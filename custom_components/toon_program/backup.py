"""Backups of the Toon configuration objects.

Before every change the integration saves the object it is about to replace.
The files live in ``<config>/toon_program_backups/<entry>/`` and are included
in a normal Home Assistant backup. They hold the object exactly as the Toon
returned it, so restoring is a plain write of that object.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    BACKUP_DIR,
    BACKUP_FORMAT,
    BACKUP_KEEP,
    BACKUP_KINDS,
    KIND_BY_ADDRESS,
)

_LOGGER = logging.getLogger(__name__)

_SAFE_REASON = re.compile(r"[^a-z0-9_]+")
_FILENAME = re.compile(
    r"^(?P<kind>[a-z]+)-(?P<stamp>\d{8}-\d{6})(?:-(?P<n>\d+))?-(?P<reason>[a-z0-9_]+)\.json$"
)


class BackupError(Exception):
    """Raised when a backup cannot be read or written."""


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """Description of one backup file."""

    filename: str
    kind: str
    created: datetime
    reason: str


def kind_for_address(internal_address: str) -> str:
    """Return the backup kind for a Toon object address."""
    return KIND_BY_ADDRESS[internal_address]


class BackupStore:
    """Read and write backups for one Toon."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialise the store."""
        self._hass = hass
        self._dir = Path(hass.config.path(BACKUP_DIR, entry_id[:8]))

    @property
    def directory(self) -> Path:
        """Return the directory that holds the backups."""
        return self._dir

    # -- public async API -------------------------------------------------

    async def async_save(self, kind: str, obj: dict[str, Any], reason: str) -> BackupInfo:
        """Save an object, unless the newest backup of this kind is identical."""
        return await self._hass.async_add_executor_job(self._save, kind, obj, reason)

    async def async_list(self) -> list[BackupInfo]:
        """Return all backups, newest first."""
        return await self._hass.async_add_executor_job(self._list)

    async def async_load(self, filename: str) -> tuple[BackupInfo, dict[str, Any]]:
        """Load one backup by file name."""
        return await self._hass.async_add_executor_job(self._load, filename)

    # -- blocking implementation (runs in the executor) --------------------

    def _list(self) -> list[BackupInfo]:
        if not self._dir.is_dir():
            return []
        found: list[BackupInfo] = []
        for path in self._dir.iterdir():
            info = _parse_filename(path.name)
            if info is not None:
                found.append(info)
        return sorted(found, key=_sort_key, reverse=True)

    def _load(self, filename: str) -> tuple[BackupInfo, dict[str, Any]]:
        info = _parse_filename(filename)
        if info is None:
            raise BackupError(f"'{filename}' is not a backup file name")
        path = self._dir / filename
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as err:
            raise BackupError(f"Backup '{filename}' does not exist") from err
        except (OSError, ValueError) as err:
            raise BackupError(f"Backup '{filename}' cannot be read: {err}") from err
        obj = document.get("object") if isinstance(document, dict) else None
        if not isinstance(obj, dict) or document.get("format") != BACKUP_FORMAT:
            raise BackupError(f"Backup '{filename}' has an unsupported format")
        return info, obj

    def _save(self, kind: str, obj: dict[str, Any], reason: str) -> BackupInfo:
        if kind not in BACKUP_KINDS:
            raise BackupError(f"Unknown backup kind '{kind}'")
        existing = [info for info in self._list() if info.kind == kind]
        if existing:
            try:
                _, newest = self._load(existing[0].filename)
            except BackupError:
                pass
            else:
                if newest == obj:
                    return existing[0]

        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        stamp = now.strftime("%Y%m%d-%H%M%S")
        reason = _SAFE_REASON.sub("_", reason.lower()).strip("_") or "backup"
        counter = ""
        path = self._dir / f"{kind}-{stamp}-{reason}.json"
        while path.exists():
            counter = str(int(counter or 0) + 1)
            path = self._dir / f"{kind}-{stamp}-{counter}-{reason}.json"

        document = {
            "format": BACKUP_FORMAT,
            "kind": kind,
            "created": now.isoformat(timespec="seconds"),
            "reason": reason,
            "object": obj,
        }
        temp = path.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
        except OSError as err:
            raise BackupError(f"Cannot write backup '{path.name}': {err}") from err

        info = _parse_filename(path.name)
        assert info is not None
        self._prune(kind)
        return info

    def _prune(self, kind: str) -> None:
        """Keep only the newest backups of one kind."""
        backups = [info for info in self._list() if info.kind == kind]
        for info in backups[BACKUP_KEEP:]:
            try:
                (self._dir / info.filename).unlink()
            except OSError as err:
                _LOGGER.debug("Could not remove old backup %s: %s", info.filename, err)


def _sort_key(info: BackupInfo) -> tuple[datetime, int]:
    """Sort by creation time, then by the counter used within one second."""
    match = _FILENAME.match(info.filename)
    return info.created, int(match["n"] or 0) if match else 0


def _parse_filename(filename: str) -> BackupInfo | None:
    """Return the backup described by a file name, or None if it is not one."""
    match = _FILENAME.match(filename)
    if match is None or match["kind"] not in BACKUP_KINDS:
        return None
    try:
        created = datetime.strptime(match["stamp"], "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return BackupInfo(
        filename=filename,
        kind=match["kind"],
        created=created,
        reason=match["reason"],
    )
