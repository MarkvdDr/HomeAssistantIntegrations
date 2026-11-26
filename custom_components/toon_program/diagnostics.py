"""Diagnostics support for the Toon Program integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_HOST
from .coordinator import ToonProgramConfigEntry

TO_REDACT = {CONF_HOST}


def _redact_text(value: str, host: str | None) -> str:
    """Replace the host wherever it appears in free text."""
    if not host:
        return value
    return value.replace(host, "**REDACTED**")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ToonProgramConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    host = entry.data.get(CONF_HOST)

    return {
        "entry": {
            "title": _redact_text(entry.title, host),
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "locale": data.locale if data else None,
        "timezone": data.timezone if data else None,
        "presets": [
            {
                "state_id": state.state_id,
                "name": state.name,
                "temperature": state.temperature,
                "dhw": state.dhw,
            }
            for state in (data.states if data else ())
        ],
        "program": data.program.as_list() if data else [],
        "backups": [
            {
                "filename": backup.filename,
                "kind": backup.kind,
                "created": backup.created.isoformat(),
                "reason": backup.reason,
            }
            for backup in coordinator.backups
        ],
        "last_update_success": coordinator.last_update_success,
        "last_exception": (
            _redact_text(repr(coordinator.last_exception), host)
            if coordinator.last_exception
            else None
        ),
    }
