"""Data coordinator for the Toon Program integration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .backup import BackupError, BackupInfo, BackupStore, kind_for_address
from .const import (
    ADDRESS_PROGRAM,
    ADDRESS_STATES,
    BACKUP_KIND_PRESETS,
    BACKUP_KINDS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .parser import PresetState, ProgramBlock, WeekProgram
from .toon_client import (
    ToonConfigClient,
    ToonConnectionError,
    ToonError,
    ToonInvalidDataError,
)

_LOGGER = logging.getLogger(__name__)

type ToonProgramConfigEntry = ConfigEntry[ToonProgramCoordinator]


def toon_day(moment: datetime) -> int:
    """Return the Toon day index (0 = Sunday) of a datetime."""
    return (moment.weekday() + 1) % 7


@dataclass
class ToonProgramData:
    """Everything the integration reads from the Toon."""

    locale: str
    timezone: str
    states: tuple[PresetState, ...]
    program: WeekProgram

    def state_for(self, state_id: int) -> PresetState | None:
        """Return the preset with ``state_id``, if present."""
        return next((s for s in self.states if s.state_id == state_id), None)

    def temperature_for(self, preset: str) -> float | None:
        """Return the temperature of a preset by name, if the Toon has it."""
        return next((s.temperature for s in self.states if s.name == preset), None)


class ToonProgramCoordinator(DataUpdateCoordinator[ToonProgramData]):
    """Poll the Toon configuration store and apply changes."""

    config_entry: ToonProgramConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ToonProgramConfigEntry,
        client: ToonConfigClient,
        store: BackupStore,
    ) -> None:
        """Initialise the coordinator."""
        self.client = client
        self.store = store
        self.backups: list[BackupInfo] = []
        self._unsub_boundary: CALLBACK_TYPE | None = None
        interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
        )
        client.backup_hook = self._async_backup_hook

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    async def _async_setup(self) -> None:
        """Load the list of existing backups once, before the first update."""
        await self._async_reload_backups()

    async def _async_update_data(self) -> ToonProgramData:
        """Read the locale, preset temperatures and week program."""
        try:
            locale = await self.client.async_get_locale()
            states = await self.client.async_get_states()
            program = await self.client.async_get_program()
        except ToonError as err:
            raise UpdateFailed(str(err)) from err

        data = ToonProgramData(
            locale=locale["locale"],
            timezone=locale["timezone"],
            states=states,
            program=program,
        )
        self.data = data  # make the new data visible to the scheduling helpers
        self._schedule_boundary()
        return data

    async def async_shutdown(self) -> None:
        """Stop polling and the block-change timer."""
        self._cancel_boundary()
        await super().async_shutdown()

    # ------------------------------------------------------------------
    # Time-based helpers
    # ------------------------------------------------------------------

    @property
    def tz(self) -> tzinfo:
        """Return the time zone of the Toon, or that of Home Assistant."""
        if self.data and (zone := dt_util.get_time_zone(self.data.timezone)):
            return zone
        return dt_util.get_default_time_zone()

    def now(self) -> datetime:
        """Return the current time in the time zone of the Toon."""
        return dt_util.now(self.tz)

    def active_block(self, now: datetime | None = None) -> ProgramBlock | None:
        """Return the program block that is active at ``now``."""
        if self.data is None:
            return None
        now = now or self.now()
        return self.data.program.block_at(toon_day(now), now.hour * 60 + now.minute)

    def next_change(self, now: datetime | None = None) -> tuple[ProgramBlock, datetime] | None:
        """Return the next block and the moment it starts."""
        if self.data is None:
            return None
        now = now or self.now()
        block, delta = self.data.program.next_block_after(toon_day(now), now.hour * 60 + now.minute)
        # The program is expressed in wall-clock time, so add the delta to the
        # wall clock and attach the zone afterwards. That keeps the block on
        # the right clock time across a daylight-saving change.
        wall = now.replace(second=0, microsecond=0, tzinfo=None) + timedelta(minutes=delta)
        return block, wall.replace(tzinfo=now.tzinfo)

    @callback
    def _schedule_boundary(self) -> None:
        """Wake the entities up when the next block of the program starts."""
        self._cancel_boundary()
        upcoming = self.next_change()
        if upcoming is None:
            return
        self._unsub_boundary = async_track_point_in_time(
            self.hass, self._boundary_reached, upcoming[1]
        )

    @callback
    def _boundary_reached(self, _now: datetime) -> None:
        """Refresh the time-dependent entities and plan the next wake-up."""
        self._unsub_boundary = None
        self.async_update_listeners()
        self._schedule_boundary()

    @callback
    def _cancel_boundary(self) -> None:
        if self._unsub_boundary is not None:
            self._unsub_boundary()
            self._unsub_boundary = None

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    async def _async_write(self, operation: Awaitable[bool]) -> bool:
        """Run a client write, translate errors and refresh afterwards."""
        try:
            changed = await operation
        except ToonInvalidDataError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_data",
                translation_placeholders={"error": str(err)},
            ) from err
        except ToonConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        except ToonError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if changed:
            await self.async_refresh()
        return changed

    async def async_set_preset_temperature(self, state_id: int, temperature: float) -> None:
        """Change one preset temperature."""
        await self._async_write(self.client.async_set_preset_temperature(state_id, temperature))

    async def async_set_schedule(self, blocks: list[ProgramBlock]) -> None:
        """Replace the complete week program."""
        await self._async_write(self.client.async_set_program(blocks))

    async def async_set_day(self, day: int, blocks: list[ProgramBlock]) -> None:
        """Replace the blocks that start on one day."""
        await self._async_write(self.client.async_set_day(day, blocks))

    # ------------------------------------------------------------------
    # Backups
    # ------------------------------------------------------------------

    async def _async_reload_backups(self) -> None:
        try:
            self.backups = await self.store.async_list()
        except OSError as err:
            _LOGGER.warning("Could not list the Toon backups: %s", err)

    async def _async_backup_hook(
        self, internal_address: str, obj: dict[str, Any], reason: str
    ) -> None:
        """Back up an object right before it is replaced."""
        await self.store.async_save(kind_for_address(internal_address), obj, reason)
        await self._async_reload_backups()
        self.async_update_listeners()

    async def async_create_backup(self) -> list[BackupInfo]:
        """Back up the week program and the presets right now."""
        try:
            created = [
                await self.store.async_save(
                    kind_for_address(address),
                    await self.client.async_get_raw(address),
                    "manual",
                )
                for address in (ADDRESS_PROGRAM, ADDRESS_STATES)
            ]
        except (ToonError, BackupError, OSError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="backup_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self._async_reload_backups()
        self.async_update_listeners()
        return created

    async def async_restore_backup(self, kind: str, filename: str | None) -> None:
        """Write a backup back to the Toon (the newest of ``kind`` by default)."""
        if kind not in BACKUP_KINDS:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_data",
                translation_placeholders={"error": f"unknown backup kind '{kind}'"},
            )
        try:
            if filename is None:
                candidates = [b for b in await self.store.async_list() if b.kind == kind]
                if not candidates:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="backup_not_found"
                    )
                filename = candidates[0].filename
            info, obj = await self.store.async_load(filename)
        except BackupError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="backup_unreadable",
                translation_placeholders={"error": str(err)},
            ) from err
        address = ADDRESS_STATES if info.kind == BACKUP_KIND_PRESETS else ADDRESS_PROGRAM
        await self._async_write(self.client.async_restore_object(address, obj, reason="restore"))


__all__ = [
    "ToonProgramConfigEntry",
    "ToonProgramCoordinator",
    "ToonProgramData",
    "toon_day",
]
