"""Sensors for the Toon week program.

The week-program sensor carries the complete schedule as attributes and is the
target of the integration's services. The other sensors describe what the
program does *right now*, so automations can react to it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    PRESET_NAMES,
    SERVICE_CREATE_BACKUP,
    SERVICE_RESTORE_BACKUP,
    SERVICE_SET_DAY,
    SERVICE_SET_SCHEDULE,
)
from .coordinator import ToonProgramConfigEntry, ToonProgramCoordinator
from .entity import ToonProgramEntity
from .parser import ProgramBlock
from .schemas import (
    CREATE_BACKUP_SCHEMA,
    RESTORE_BACKUP_SCHEMA,
    SET_DAY_SCHEMA,
    SET_SCHEDULE_SCHEMA,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ToonProgramConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors and the integration's entity services."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ToonWeekProgramSensor(coordinator, entry),
            ToonCurrentPresetSensor(coordinator, entry),
            ToonProgramTemperatureSensor(coordinator, entry),
            ToonNextPresetSensor(coordinator, entry),
            ToonNextChangeSensor(coordinator, entry),
        ]
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_SCHEDULE, SET_SCHEDULE_SCHEMA, "async_set_schedule"
    )
    platform.async_register_entity_service(SERVICE_SET_DAY, SET_DAY_SCHEMA, "async_set_day")
    platform.async_register_entity_service(
        SERVICE_CREATE_BACKUP, CREATE_BACKUP_SCHEMA, "async_create_backup"
    )
    platform.async_register_entity_service(
        SERVICE_RESTORE_BACKUP, RESTORE_BACKUP_SCHEMA, "async_restore_backup"
    )


class ToonSensor(ToonProgramEntity, SensorEntity):
    """Base class of the Toon sensors.

    The service handlers live here so that any sensor of the integration is a
    valid service target, not only the week-program sensor.
    """

    async def async_set_schedule(self, blocks: list[ProgramBlock]) -> None:
        """Replace the complete week program."""
        await self.coordinator.async_set_schedule(blocks)

    async def async_set_day(self, day: int, blocks: list[tuple[int, str]]) -> None:
        """Replace the blocks that start on one day."""
        await self.coordinator.async_set_day(
            day,
            [ProgramBlock(day=day, minutes=minutes, preset=preset) for minutes, preset in blocks],
        )

    async def async_create_backup(self) -> None:
        """Back up the week program and the presets."""
        await self.coordinator.async_create_backup()

    async def async_restore_backup(self, kind: str, filename: str | None = None) -> None:
        """Restore a backup."""
        await self.coordinator.async_restore_backup(kind, filename)


class ToonWeekProgramSensor(ToonSensor):
    """The Toon week program as a sensor with attributes."""

    _attr_translation_key = "week_program"
    _attr_icon = "mdi:calendar-week"
    # The schedule is large and rarely changes: keep it out of the recorder.
    _unrecorded_attributes = frozenset(
        {"blocks", "days", "preset_temperatures", "preset_entities", "backups"}
    )

    def __init__(self, coordinator: ToonProgramCoordinator, entry: ToonProgramConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, "week_program")
        self._entry = entry

    @property
    def native_value(self) -> int | None:
        """Return the number of blocks in the week program."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.program.blocks)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the full week program."""
        data = self.coordinator.data
        if data is None:
            return None
        registry = er.async_get(self.hass)
        preset_entities = {
            name: entity_id
            for name in PRESET_NAMES
            if (
                entity_id := registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_preset_{name}"
                )
            )
        }
        return {
            "locale": data.locale,
            "timezone": data.timezone,
            "blocks": data.program.as_list(),
            "days": data.program.per_day(),
            "preset_temperatures": {state.name: state.temperature for state in data.states},
            "preset_entities": preset_entities,
            "backups": [backup.filename for backup in self.coordinator.backups],
        }


class ToonCurrentPresetSensor(ToonSensor):
    """The preset that the week program applies right now."""

    _attr_translation_key = "current_preset"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(PRESET_NAMES)

    def __init__(self, coordinator: ToonProgramCoordinator, entry: ToonProgramConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, "current_preset")

    @property
    def native_value(self) -> str | None:
        """Return the active preset."""
        block = self.coordinator.active_block()
        return None if block is None else block.preset


class ToonProgramTemperatureSensor(ToonSensor):
    """The temperature that the week program asks for right now."""

    _attr_translation_key = "program_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: ToonProgramCoordinator, entry: ToonProgramConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, "program_temperature")

    @property
    def native_value(self) -> float | None:
        """Return the temperature of the active preset."""
        block = self.coordinator.active_block()
        if block is None or self.coordinator.data is None:
            return None
        return self.coordinator.data.temperature_for(block.preset)


class ToonNextPresetSensor(ToonSensor):
    """The preset of the next block of the week program."""

    _attr_translation_key = "next_preset"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(PRESET_NAMES)

    def __init__(self, coordinator: ToonProgramCoordinator, entry: ToonProgramConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, "next_preset")

    @property
    def native_value(self) -> str | None:
        """Return the next preset."""
        upcoming = self.coordinator.next_change()
        return None if upcoming is None else upcoming[0].preset

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the temperature that goes with the next preset."""
        upcoming = self.coordinator.next_change()
        if upcoming is None or self.coordinator.data is None:
            return None
        return {"temperature": self.coordinator.data.temperature_for(upcoming[0].preset)}


class ToonNextChangeSensor(ToonSensor):
    """The moment the week program switches to the next preset."""

    _attr_translation_key = "next_change"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: ToonProgramCoordinator, entry: ToonProgramConfigEntry) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, entry, "next_change")

    @property
    def native_value(self) -> datetime | None:
        """Return the start of the next block."""
        upcoming = self.coordinator.next_change()
        return None if upcoming is None else upcoming[1]
