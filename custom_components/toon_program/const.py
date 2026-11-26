"""Constants for the Toon Program integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "toon_program"
DEFAULT_NAME: Final = "Toon Program"

CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_NAME: Final = "name"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_PORT: Final = 80
DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 86400
DEFAULT_TIMEOUT: Final = 10

# The Toon configuration store is addressed by package + internalAddress.
PACKAGE: Final = "happ_thermstat"
ADDRESS_STATES: Final = "thermostatStates"
ADDRESS_PROGRAM: Final = "thermostatProgram"

# Toon preset states, as used in thermostatStates and thermostatProgram.
PRESET_STATES: Final[dict[int, str]] = {
    0: "comfort",
    1: "home",
    2: "sleep",
    3: "away",
    4: "holiday",
}
PRESET_NAMES: Final[tuple[str, ...]] = tuple(PRESET_STATES.values())
PRESET_IDS: Final[dict[str, int]] = {name: key for key, name in PRESET_STATES.items()}

# Human readable preset names, used for calendar events.
PRESET_LABELS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "comfort": "Comfort",
        "home": "Home",
        "sleep": "Sleep",
        "away": "Away",
        "holiday": "Holiday",
    },
    "nl": {
        "comfort": "Comfort",
        "home": "Thuis",
        "sleep": "Slapen",
        "away": "Weg",
        "holiday": "Vakantie",
    },
}

# The Toon week program uses day 0 = Sunday, 6 = Saturday.
DAY_NAMES: Final[tuple[str, ...]] = (
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
)
DAY_ALIASES: Final[dict[str, int]] = {
    "sunday": 0,
    "zondag": 0,
    "sun": 0,
    "zo": 0,
    "monday": 1,
    "maandag": 1,
    "mon": 1,
    "ma": 1,
    "tuesday": 2,
    "dinsdag": 2,
    "tue": 2,
    "di": 2,
    "wednesday": 3,
    "woensdag": 3,
    "wed": 3,
    "wo": 3,
    "thursday": 4,
    "donderdag": 4,
    "thu": 4,
    "do": 4,
    "friday": 5,
    "vrijdag": 5,
    "fri": 5,
    "vr": 5,
    "saturday": 6,
    "zaterdag": 6,
    "sat": 6,
    "za": 6,
}

# Range the Toon accepts for a preset temperature (in degrees Celsius).
MIN_TEMPERATURE: Final = 5.0
MAX_TEMPERATURE: Final = 30.0
TEMPERATURE_STEP: Final = 0.5

MINUTES_PER_DAY: Final = 24 * 60
MINUTES_PER_WEEK: Final = 7 * MINUTES_PER_DAY
MAX_BLOCKS: Final = 100

# Services.
SERVICE_SET_SCHEDULE: Final = "set_schedule"
SERVICE_SET_DAY: Final = "set_day"
SERVICE_CREATE_BACKUP: Final = "create_backup"
SERVICE_RESTORE_BACKUP: Final = "restore_backup"

# Backups of the Toon objects, kept in the Home Assistant config directory.
BACKUP_DIR: Final = "toon_program_backups"
BACKUP_KEEP: Final = 20
BACKUP_FORMAT: Final = 1
BACKUP_KIND_PROGRAM: Final = "program"
BACKUP_KIND_PRESETS: Final = "presets"
BACKUP_KINDS: Final = (BACKUP_KIND_PROGRAM, BACKUP_KIND_PRESETS)
KIND_BY_ADDRESS: Final[dict[str, str]] = {
    ADDRESS_PROGRAM: BACKUP_KIND_PROGRAM,
    ADDRESS_STATES: BACKUP_KIND_PRESETS,
}

# Lovelace card, served by the integration itself.
CARD_URL_BASE: Final = "/toon_program"
CARD_FILENAME: Final = "toon-program-card.js"
