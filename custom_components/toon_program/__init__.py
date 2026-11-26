"""The Toon Program integration.

Reads the week program and the temperature presets from a rooted Toon and
writes changes back through the local ``hcb_config`` HTTP API.
"""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .backup import BackupStore
from .card import async_register_card
from .const import DEFAULT_PORT, DOMAIN
from .coordinator import ToonProgramConfigEntry, ToonProgramCoordinator
from .toon_client import ToonConfigClient

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# The preset numbers and the backup button are created first, so the week
# program sensor can point to the number entities in its attributes.
_FIRST_PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.BUTTON]
_LAST_PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]
PLATFORMS: list[Platform] = [*_FIRST_PLATFORMS, *_LAST_PLATFORMS]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the Lovelace card."""
    try:
        await async_register_card(hass)
    except Exception:
        _LOGGER.warning("Could not register the Toon Program card", exc_info=True)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ToonProgramConfigEntry) -> bool:
    """Set up one Toon from a config entry."""
    client = ToonConfigClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    coordinator = ToonProgramCoordinator(hass, entry, client, BackupStore(hass, entry.entry_id))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Ensure the Lovelace card is registered (in addition to async_setup, which
    # only runs for YAML-based setup). The registration is idempotent.
    await async_register_card(hass)

    await hass.config_entries.async_forward_entry_setups(entry, _FIRST_PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, _LAST_PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.debug(
        "Toon Program set up for %s (%s blocks, %s presets)",
        entry.title,
        len(coordinator.data.program.blocks),
        len(coordinator.data.states),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ToonProgramConfigEntry) -> bool:
    """Unload one Toon."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ToonProgramConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
