"""Button to back up the Toon configuration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ToonProgramConfigEntry, ToonProgramCoordinator
from .entity import ToonProgramEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ToonProgramConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the backup button."""
    async_add_entities([ToonBackupButton(entry.runtime_data, entry)])


class ToonBackupButton(ToonProgramEntity, ButtonEntity):
    """Save the week program and the presets to the backup folder."""

    _attr_translation_key = "create_backup"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ToonProgramCoordinator, entry: ToonProgramConfigEntry) -> None:
        """Initialise the button."""
        super().__init__(coordinator, entry, "create_backup")

    async def async_press(self) -> None:
        """Create a backup."""
        await self.coordinator.async_create_backup()
