"""Async client for the Toon ``hcb_config`` HTTP API.

The Toon is a small, slow device. This client therefore

* serialises every request, so the device never handles two at once;
* retries reads on connection problems and server errors;
* caches the uuids of the objects it needs, so a poll is two requests;
* verifies every write by reading the object back, and puts the original
  object back when the Toon did not apply the change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from typing import Any

import aiohttp

from .const import (
    ADDRESS_PROGRAM,
    ADDRESS_STATES,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    PACKAGE,
)
from .parser import (
    PresetState,
    ProgramBlock,
    ToonFormatError,
    WeekProgram,
    build_program_object,
    build_states_object,
    object_uuid,
    parse_program,
    parse_states,
    replace_day,
    to_xml,
    validate_blocks,
)

_LOGGER = logging.getLogger(__name__)

# Delays (in seconds) between read-back attempts after a write. The Toon
# stores configuration synchronously, but a short retry avoids a false
# mismatch when the device is busy.
_VERIFY_DELAYS: tuple[float, ...] = (0.0, 0.2, 0.5, 1.0, 2.0)

# Reads are retried on connection problems and on these server errors.
_READ_RETRIES = 2
_RETRY_DELAY = 0.5
_RETRY_STATUSES = frozenset({500, 502, 503, 504})

# A week program travels in the query string of a GET request. When the Toon
# rejects that as too large, the same request is sent as a POST.
_TOO_LARGE_STATUSES = frozenset({400, 413, 414, 431})

BackupHook = Callable[[str, dict[str, Any], str], Awaitable[None]]


class ToonError(Exception):
    """Base error for the Toon configuration API."""


class ToonConnectionError(ToonError):
    """Raised when the Toon cannot be reached."""


class ToonApiError(ToonError):
    """Raised when the Toon answers with an error or unexpected data."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        invalid_body: bool = False,
    ) -> None:
        """Initialise the error."""
        super().__init__(message)
        self.status = status
        self.invalid_body = invalid_body


class ToonInvalidDataError(ToonError):
    """Raised when the requested change is invalid; nothing was sent."""


class ToonConfigClient:
    """Small client for the configuration endpoints of a rooted Toon.

    The Toon exposes its configuration store over HTTP:

    * ``getLocale``
    * ``getObjectConfigTree`` -- read an object as a tree (used for the uuid)
    * ``getObjectConfig`` -- read one object as a node list
    * ``setObjectConfig`` -- write one or more objects
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._host = host
        self._port = port
        self._url = f"http://{host}:{port}/hcb_config"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        # One request at a time; one read-modify-write sequence at a time.
        self._request_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._uuids: dict[str, str] = {}
        self._locale: dict[str, str] | None = None
        # The Toon ignores a write whose packageRevision does not increase.
        self._revision = 0
        self.backup_hook: BackupHook | None = None

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the configured port."""
        return self._port

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    async def _request_once(self, params: dict[str, str], method: str = "GET") -> dict[str, Any]:
        """Perform one request and return the decoded JSON answer."""
        action = params.get("action")
        try:
            async with self._request_lock:
                if method == "POST":
                    request = self._session.post(self._url, data=params, timeout=self._timeout)
                else:
                    request = self._session.get(self._url, params=params, timeout=self._timeout)
                async with request as response:
                    status = response.status
                    text = await response.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ToonConnectionError(
                f"Cannot reach the Toon at {self._host}:{self._port}: {err or type(err).__name__}"
            ) from err

        if status != 200:
            raise ToonApiError(
                f"The Toon returned HTTP {status} for action '{action}'",
                status=status,
            )

        try:
            data = json.loads(text)
        except ValueError as err:
            raise ToonApiError(
                f"The Toon returned invalid JSON for action '{action}': {text[:200]!r}",
                invalid_body=True,
            ) from err

        if not isinstance(data, dict):
            raise ToonApiError(
                f"The Toon returned an unexpected answer for action '{action}': {text[:200]!r}",
                invalid_body=True,
            )
        if data.get("result") == "error":
            reason = data.get("error") or data.get("reason") or "unknown error"
            raise ToonApiError(f"The Toon refused action '{action}': {reason}")
        return data

    async def _request(
        self,
        params: dict[str, str],
        *,
        retries: int = _READ_RETRIES,
        method: str = "GET",
    ) -> dict[str, Any]:
        """Perform a request, retrying transient failures."""
        attempt = 0
        while True:
            try:
                return await self._request_once(params, method)
            except ToonConnectionError:
                if attempt >= retries:
                    raise
            except ToonApiError as err:
                if err.status not in _RETRY_STATUSES or attempt >= retries:
                    raise
            attempt += 1
            await asyncio.sleep(_RETRY_DELAY * attempt)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    async def async_get_locale(self, *, refresh: bool = False) -> dict[str, str]:
        """Return the locale and timezone of the Toon (cached)."""
        if self._locale is not None and not refresh:
            return self._locale
        data = await self._request({"action": "getLocale"})
        self._locale = {
            "locale": str(data.get("locale", "")),
            "timezone": str(data.get("timezone", "")),
        }
        return self._locale

    async def async_get_tree(
        self, internal_address: str, *, retries: int = _READ_RETRIES
    ) -> dict[str, Any]:
        """Return an object as a tree."""
        return await self._request(
            {
                "action": "getObjectConfigTree",
                "package": PACKAGE,
                "internalAddress": internal_address,
            },
            retries=retries,
        )

    async def _async_uuid(self, internal_address: str, *, refresh: bool, retries: int) -> str:
        """Return the uuid of an object, from the cache when possible."""
        if not refresh and (cached := self._uuids.get(internal_address)):
            return cached
        tree = await self.async_get_tree(internal_address, retries=retries)
        uuid = _tree_uuid(tree, internal_address)
        self._uuids[internal_address] = uuid
        return uuid

    async def async_get_object(
        self, internal_address: str, *, retries: int = _READ_RETRIES
    ) -> dict[str, Any]:
        """Return one configuration object as a node list."""
        for attempt in (0, 1):
            was_cached = internal_address in self._uuids
            uuid = await self._async_uuid(internal_address, refresh=attempt > 0, retries=retries)
            try:
                return await self._request(
                    {
                        "action": "getObjectConfig",
                        "uuid": uuid,
                        "package": PACKAGE,
                        "internalAddress": internal_address,
                    },
                    retries=retries,
                )
            except ToonApiError:
                # The cached uuid may be stale (for example after a factory
                # reset of the Toon). Look it up once more before giving up.
                if attempt == 1 or not was_cached:
                    raise
        raise ToonApiError(f"Cannot read '{internal_address}'")  # pragma: no cover

    async def async_get_states(self, *, retries: int = _READ_RETRIES) -> tuple[PresetState, ...]:
        """Return the preset temperatures."""
        obj = await self.async_get_object(ADDRESS_STATES, retries=retries)
        try:
            return parse_states(obj)
        except ToonFormatError as err:
            raise ToonApiError(f"Unexpected thermostatStates object: {err}") from err

    async def async_get_program(self, *, retries: int = _READ_RETRIES) -> WeekProgram:
        """Return the week program."""
        obj = await self.async_get_object(ADDRESS_PROGRAM, retries=retries)
        try:
            return parse_program(obj)
        except ToonFormatError as err:
            raise ToonApiError(f"Unexpected thermostatProgram object: {err}") from err

    async def async_get_raw(self, internal_address: str) -> dict[str, Any]:
        """Return an object exactly as the Toon reports it (for backups)."""
        return await self.async_get_object(internal_address)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def _next_revision(self) -> int:
        """Return a package revision higher than the one used for the previous write."""
        self._revision = max(self._revision + 1, int(time.time()))
        return self._revision

    async def async_set_object(self, obj: dict[str, Any]) -> None:
        """Write one configuration object back to the Toon.

        The Toon takes the XML form of a ``Config`` document and only applies it
        when ``packageRevision`` is higher than the revision it holds. A JSON
        body is silently ignored, which is why every write is verified.
        """
        payload = to_xml(obj, self._next_revision())
        params = {"action": "setObjectConfig", "config": payload}
        try:
            await self._request(params, retries=0)
        except ToonApiError as err:
            if err.status in _TOO_LARGE_STATUSES:
                _LOGGER.warning(
                    "The Toon rejected the write as too large (HTTP %s); retrying as POST",
                    err.status,
                )
                await self._request(params, retries=0, method="POST")
            elif err.invalid_body:
                # Some firmware answers a write without JSON. The read-back
                # that follows every write decides whether it worked.
                _LOGGER.debug("The Toon answered a write without valid JSON")
            else:
                raise

    async def async_set_preset_temperature(
        self, state_id: int, temperature: float, *, reason: str = "set_preset"
    ) -> bool:
        """Change one preset temperature and verify the result.

        Returns ``False`` when the preset already had that temperature.
        """
        temperature = round(temperature, 2)
        if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
            raise ToonInvalidDataError(
                f"Temperature {temperature} is outside {MIN_TEMPERATURE}-{MAX_TEMPERATURE} °C"
            )

        async with self._write_lock:
            obj = await self.async_get_object(ADDRESS_STATES)
            try:
                states = parse_states(obj)
            except ToonFormatError as err:
                raise ToonApiError(f"Unexpected thermostatStates object: {err}") from err

            current = next((s for s in states if s.state_id == state_id), None)
            if current is None:
                raise ToonInvalidDataError(f"The Toon has no preset with id {state_id}")
            if abs(current.temperature - temperature) < 0.005:
                return False

            updated = tuple(
                replace(state, temperature=temperature) if state.state_id == state_id else state
                for state in states
            )
            try:
                payload = build_states_object(obj, updated)
            except (ToonFormatError, ValueError) as err:
                raise ToonApiError(f"Cannot build thermostatStates: {err}") from err

            expected = _states_signature(updated)
            await self._write_and_verify(
                ADDRESS_STATES,
                obj,
                payload,
                lambda: self._states_match(expected),
                reason,
                f"temperature of preset '{current.name}'",
            )
            return True

    async def async_set_program(
        self, blocks: Sequence[ProgramBlock], *, reason: str = "set_schedule"
    ) -> bool:
        """Replace the week program and verify the result.

        Returns ``False`` when the Toon already had exactly this program.
        """
        return await self._update_program(lambda _program: blocks, reason)

    async def async_set_day(
        self, day: int, blocks: Sequence[ProgramBlock], *, reason: str = "set_day"
    ) -> bool:
        """Replace the blocks that start on one day.

        The program is read from the Toon itself, inside the write lock, so a
        change made on the device in the meantime is not overwritten.
        """
        return await self._update_program(lambda program: replace_day(program, day, blocks), reason)

    async def _update_program(
        self,
        build: Callable[[WeekProgram], Sequence[ProgramBlock]],
        reason: str,
    ) -> bool:
        """Read, change, write and verify the week program."""
        async with self._write_lock:
            obj = await self.async_get_object(ADDRESS_PROGRAM)
            try:
                current = parse_program(obj)
            except ToonFormatError as err:
                raise ToonApiError(f"Unexpected thermostatProgram object: {err}") from err

            try:
                ordered = validate_blocks(build(current))
                expected = WeekProgram(ordered).timeline()
            except (ToonFormatError, ValueError) as err:
                raise ToonInvalidDataError(f"Invalid week program: {err}") from err

            if current.timeline() == expected:
                return False

            try:
                payload = build_program_object(obj, ordered)
            except (ToonFormatError, ValueError) as err:
                raise ToonApiError(f"Cannot build thermostatProgram: {err}") from err

            await self._write_and_verify(
                ADDRESS_PROGRAM,
                obj,
                payload,
                lambda: self._program_matches(expected),
                reason,
                "week program",
            )
            return True

    async def async_restore_object(
        self, internal_address: str, backup: dict[str, Any], *, reason: str = "restore"
    ) -> bool:
        """Write a backed-up object back to the Toon and verify the result.

        Returns ``False`` when the Toon already holds exactly this object.
        """
        if internal_address not in (ADDRESS_PROGRAM, ADDRESS_STATES):
            raise ToonInvalidDataError(f"Cannot restore '{internal_address}'")

        try:
            if internal_address == ADDRESS_PROGRAM:
                expected_program = parse_program(backup).timeline()
            else:
                expected_states = _states_signature(parse_states(backup))
        except ToonFormatError as err:
            raise ToonInvalidDataError(f"The backup is not usable: {err}") from err

        async with self._write_lock:
            current = await self.async_get_object(internal_address)
            current_uuid, backup_uuid = object_uuid(current), object_uuid(backup)
            if current_uuid and backup_uuid and current_uuid != backup_uuid:
                raise ToonInvalidDataError(
                    "The backup belongs to a different Toon (the uuid differs)"
                )
            if current == backup:
                return False

            if internal_address == ADDRESS_PROGRAM:
                check = lambda: self._program_matches(expected_program)  # noqa: E731
                label = "week program"
            else:
                check = lambda: self._states_match(expected_states)  # noqa: E731
                label = "preset temperatures"
            await self._write_and_verify(internal_address, current, backup, check, reason, label)
            return True

    async def _write_and_verify(
        self,
        internal_address: str,
        old: dict[str, Any],
        new: dict[str, Any],
        check: Callable[[], Awaitable[bool]],
        reason: str,
        label: str,
    ) -> None:
        """Write ``new``, verify it, and put ``old`` back when it did not apply."""
        if self.backup_hook is not None:
            try:
                await self.backup_hook(internal_address, old, reason)
            except Exception:
                _LOGGER.warning("Could not back up %s before writing", label, exc_info=True)

        write_error: ToonError | None = None
        try:
            await self.async_set_object(new)
        except ToonError as err:
            write_error = err

        # After a connection error the device is probably unreachable: one
        # quick look is enough, no need to wait through the full schedule.
        delays = (0.0,) if isinstance(write_error, ToonConnectionError) else _VERIFY_DELAYS
        result = await self._verify(check, delays)

        if result:
            if write_error is not None:
                _LOGGER.warning(
                    "The Toon reported an error while writing the %s, but the "
                    "change was applied: %s",
                    label,
                    write_error,
                )
            return

        if result is None:
            # Not reachable at all, so there is nothing that can be restored.
            raise ToonConnectionError(
                f"Lost the connection to the Toon while changing the {label}; the result is unknown"
            ) from write_error

        # Reachable, but the change did not arrive: put the original back so a
        # failed write cannot leave a partially applied configuration behind.
        try:
            await self.async_set_object(old)
        except ToonError as err:
            _LOGGER.error("Could not restore the %s: %s", label, err)
            restored = "and restoring the previous value failed"
        else:
            restored = "the previous value was restored"
        raise ToonApiError(f"The Toon did not apply the new {label}; {restored}") from write_error

    async def _verify(
        self, check: Callable[[], Awaitable[bool]], delays: tuple[float, ...]
    ) -> bool | None:
        """Return True when ``check`` passes, False when it fails, None if unreachable."""
        reachable = False
        for delay in delays:
            if delay:
                await asyncio.sleep(delay)
            try:
                if await check():
                    return True
                reachable = True
            except ToonConnectionError:
                continue
            except (ToonError, ToonFormatError):
                reachable = True
        return False if reachable else None

    async def _program_matches(self, expected: tuple[str, ...]) -> bool:
        """Return True when the Toon holds the expected week program."""
        program = await self.async_get_program(retries=0)
        return program.timeline() == expected

    async def _states_match(self, expected: frozenset[tuple[int, float, bool]]) -> bool:
        """Return True when the Toon holds the expected preset temperatures."""
        states = await self.async_get_states(retries=0)
        return _states_signature(states) == expected


def _states_signature(
    states: Sequence[PresetState],
) -> frozenset[tuple[int, float, bool]]:
    """Return a comparable representation of a set of presets."""
    return frozenset((s.state_id, round(s.temperature, 2), s.dhw) for s in states)


def _tree_uuid(tree: dict[str, Any], internal_address: str) -> str:
    """Extract the uuid from a ``getObjectConfigTree`` answer."""
    uuid = tree.get("uuid")
    if isinstance(uuid, list) and uuid:
        return str(uuid[0])
    raise ToonApiError(f"The Toon did not return a uuid for '{internal_address}'")
