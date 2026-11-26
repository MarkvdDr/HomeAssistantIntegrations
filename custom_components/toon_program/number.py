"""Number entities for the Toon temperature presets."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_TEMPERATURE, MIN_TEMPERATURE, PRESET_STATES, TEMPERATURE_STEP
from .coordinator import ToonProgramConfigEntry, ToonProgramCoordinator
from .entity import ToonProgramEntity
from .parser import PresetState

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ToonProgramConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one number entity per Toon preset."""
    coordinator = entry.runtime_data
    async_add_entities(
        ToonPresetTemperature(coordinator, entry, state_id) for state_id in PRESET_STATES
    )


class ToonPresetTemperature(ToonProgramEntity, NumberEntity):
    """The temperature of one Toon preset."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_min_value = MIN_TEMPERATURE
    _attr_native_max_value = MAX_TEMPERATURE
    _attr_native_step = TEMPERATURE_STEP
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: ToonProgramCoordinator,
        entry: ToonProgramConfigEntry,
        state_id: int,
    ) -> None:
        """Initialise the entity."""
        name = PRESET_STATES[state_id]
        super().__init__(coordinator, entry, f"preset_{name}")
        self._state_id = state_id
        self._attr_translation_key = f"preset_{name}"

    @property
    def _preset(self) -> PresetState | None:
        """Return the current preset state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.state_for(self._state_id)

    @property
    def available(self) -> bool:
        """Return whether the preset is present on the Toon."""
        return super().available and self._preset is not None

    @property
    def native_value(self) -> float | None:
        """Return the preset temperature."""
        preset = self._preset
        return None if preset is None else preset.temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra information about the preset."""
        preset = self._preset
        return {
            "preset": PRESET_STATES[self._state_id],
            "state_id": self._state_id,
            "dhw": None if preset is None else preset.dhw,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Change the preset temperature on the Toon."""
        await self.coordinator.async_set_preset_temperature(self._state_id, value)
