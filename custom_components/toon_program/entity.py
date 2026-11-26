"""Shared entity base for the Toon Program integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ToonProgramCoordinator


class ToonProgramEntity(CoordinatorEntity[ToonProgramCoordinator]):
    """Base class for entities of one Toon."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ToonProgramCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        client = coordinator.client
        port = "" if client.port == 80 else f":{client.port}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Eneco",
            model="Toon",
            configuration_url=f"http://{client.host}{port}",
        )
