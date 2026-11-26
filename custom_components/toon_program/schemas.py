"""Validation of the service data of the Toon Program integration."""

from __future__ import annotations

from datetime import time as dt_time
from typing import Any

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    BACKUP_KIND_PRESETS,
    BACKUP_KIND_PROGRAM,
    DAY_ALIASES,
    PRESET_IDS,
)
from .parser import ProgramBlock


def parse_day(value: Any) -> int:
    """Validate a day name or number and return the Toon day index."""
    if isinstance(value, bool):
        raise vol.Invalid(f"Invalid day: {value!r}")
    if isinstance(value, int):
        if 0 <= value <= 6:
            return value
        raise vol.Invalid(f"Invalid day: {value!r}")
    if isinstance(value, str):
        key = value.strip().lower().rstrip(".")
        if key in DAY_ALIASES:
            return DAY_ALIASES[key]
    raise vol.Invalid(f"Invalid day: {value!r} (use sunday..saturday or zondag..zaterdag)")


def parse_time(value: Any) -> int:
    """Validate a time and return the minutes since midnight."""
    if isinstance(value, dt_time):
        return value.hour * 60 + value.minute
    if isinstance(value, str):
        parts = value.strip().split(":")
        if len(parts) in (2, 3):
            try:
                hour = int(parts[0])
                minute = int(parts[1])
            except ValueError:
                pass
            else:
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return hour * 60 + minute
    raise vol.Invalid(f"Invalid time: {value!r} (use HH:MM)")


def parse_preset(value: Any) -> str:
    """Validate a preset name."""
    if isinstance(value, str):
        key = value.strip().lower()
        if key in PRESET_IDS:
            return key
    raise vol.Invalid(f"Invalid preset: {value!r} (use {'/'.join(PRESET_IDS)})")


BLOCK_SCHEMA = vol.Schema(
    {
        vol.Required("day"): parse_day,
        vol.Required("time"): parse_time,
        vol.Required("preset"): parse_preset,
    }
)

DAY_BLOCK_SCHEMA = vol.Schema(
    {
        vol.Required("time"): parse_time,
        vol.Required("preset"): parse_preset,
    }
)


def _schedule_blocks(value: list[dict[str, Any]]) -> list[ProgramBlock]:
    """Convert validated service data to program blocks."""
    return [
        ProgramBlock(day=item["day"], minutes=item["time"], preset=item["preset"]) for item in value
    ]


def _day_blocks(value: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Convert validated service data to (minutes, preset) tuples."""
    return [(item["time"], item["preset"]) for item in value]


SET_SCHEDULE_SCHEMA = {
    vol.Required("blocks"): vol.All(cv.ensure_list, [BLOCK_SCHEMA], _schedule_blocks),
}

SET_DAY_SCHEMA = {
    vol.Required("day"): parse_day,
    vol.Required("blocks"): vol.All(cv.ensure_list, [DAY_BLOCK_SCHEMA], _day_blocks),
}

CREATE_BACKUP_SCHEMA: dict[Any, Any] = {}

RESTORE_BACKUP_SCHEMA = {
    vol.Optional("kind", default=BACKUP_KIND_PROGRAM): vol.In(
        (BACKUP_KIND_PROGRAM, BACKUP_KIND_PRESETS)
    ),
    vol.Optional("filename"): cv.string,
}
