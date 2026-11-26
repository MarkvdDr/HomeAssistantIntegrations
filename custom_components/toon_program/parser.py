"""Parsing and serialisation of the Toon ``hcb_config`` objects.

The Toon returns configuration objects as a JSON rendering of an XML node
tree. Two shapes exist:

``getObjectConfigTree`` (the tree of an object)::

    {"schedule": [{"entry": [{"startMin": ["30"], ...}]}], "package": ["..."]}

``getObjectConfig`` (a single object as a node list)::

    {"device": [{"schedule": [{"entry": [{"startMin": "30", ...}]}]},
                {"package": "happ_thermstat"}, ...]}

This module is deliberately free of Home Assistant and aiohttp imports so it
can be unit-tested on its own.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .const import (
    DAY_NAMES,
    MAX_BLOCKS,
    MINUTES_PER_DAY,
    MINUTES_PER_WEEK,
    PRESET_IDS,
    PRESET_STATES,
)


class ToonFormatError(ValueError):
    """The Toon returned an object this integration does not understand."""


@dataclass(frozen=True, slots=True)
class PresetState:
    """One temperature preset as stored in ``thermostatStates``."""

    state_id: int
    temperature: float
    dhw: bool = True

    @property
    def name(self) -> str:
        """Return the Toon name of this preset."""
        return PRESET_STATES.get(self.state_id, f"state_{self.state_id}")


@dataclass(frozen=True, slots=True)
class ProgramBlock:
    """One block of the week program.

    A block has a start (day + time) and the preset that applies from that
    moment until the next block starts. The Toon stores the end explicitly,
    but it is always the start of the next block, so it is derived here.
    """

    day: int
    minutes: int
    preset: str

    @property
    def hour(self) -> int:
        """Return the start hour."""
        return self.minutes // 60

    @property
    def minute(self) -> int:
        """Return the start minute."""
        return self.minutes % 60

    @property
    def time(self) -> str:
        """Return the start time as ``HH:MM``."""
        return f"{self.hour:02d}:{self.minute:02d}"

    @property
    def day_name(self) -> str:
        """Return the English day name."""
        return DAY_NAMES[self.day]

    @property
    def week_minute(self) -> int:
        """Return the start as minutes since Sunday 00:00."""
        return self.day * MINUTES_PER_DAY + self.minutes

    def as_dict(self) -> dict[str, Any]:
        """Return a serialisable representation."""
        return {"day": self.day_name, "time": self.time, "preset": self.preset}


@dataclass(frozen=True, slots=True)
class WeekProgram:
    """A complete Toon week program."""

    blocks: tuple[ProgramBlock, ...]

    def __post_init__(self) -> None:
        """Validate the program."""
        if not self.blocks:
            raise ToonFormatError("The week program contains no blocks")
        for block in self.blocks:
            if not 0 <= block.day <= 6:
                raise ToonFormatError(f"Invalid day {block.day} in week program")
            if not 0 <= block.minutes < MINUTES_PER_DAY:
                raise ToonFormatError(f"Invalid time {block.time} in week program")
            if block.preset not in PRESET_IDS:
                raise ToonFormatError(f"Invalid preset {block.preset!r} in week program")
        if len({(b.day, b.minutes) for b in self.blocks}) != len(self.blocks):
            raise ToonFormatError("The week program contains duplicate blocks")

    @property
    def sorted_blocks(self) -> tuple[ProgramBlock, ...]:
        """Return the blocks in weekly order."""
        return tuple(sorted(self.blocks, key=lambda block: block.week_minute))

    def for_day(self, day: int) -> tuple[ProgramBlock, ...]:
        """Return the blocks that start on ``day``."""
        return tuple(block for block in self.sorted_blocks if block.day == day)

    def next_block(self, block: ProgramBlock) -> ProgramBlock:
        """Return the block that follows ``block``, wrapping the week."""
        ordered = self.sorted_blocks
        for candidate in ordered:
            if candidate.week_minute > block.week_minute:
                return candidate
        return ordered[0]

    def duration(self, block: ProgramBlock) -> int:
        """Return how many minutes ``block`` lasts."""
        delta = self.next_block(block).week_minute - block.week_minute
        return delta if delta > 0 else delta + MINUTES_PER_WEEK

    def block_at(self, day: int, minutes: int) -> ProgramBlock:
        """Return the block that is active at ``day``/``minutes``."""
        target = day * MINUTES_PER_DAY + minutes
        active = self.sorted_blocks[-1]
        for block in self.sorted_blocks:
            if block.week_minute <= target:
                active = block
            else:
                break
        return active

    def next_block_after(self, day: int, minutes: int) -> tuple[ProgramBlock, int]:
        """Return the next block that starts after ``day``/``minutes``.

        The second value is the number of minutes until that block starts. The
        week wraps, so there is always a next block (for a program with a
        single block it is that block, one week later).
        """
        target = day * MINUTES_PER_DAY + minutes
        ordered = self.sorted_blocks
        for block in ordered:
            if block.week_minute > target:
                return block, block.week_minute - target
        first = ordered[0]
        return first, first.week_minute + MINUTES_PER_WEEK - target

    def as_list(self) -> list[dict[str, Any]]:
        """Return the full program as a list of dictionaries."""
        result: list[dict[str, Any]] = []
        for block in self.sorted_blocks:
            following = self.next_block(block)
            result.append(
                {
                    "day": block.day_name,
                    "time": block.time,
                    "preset": block.preset,
                    "end_day": following.day_name,
                    "end_time": following.time,
                    "duration_minutes": self.duration(block),
                }
            )
        return result

    def per_day(self) -> dict[str, list[dict[str, Any]]]:
        """Return the program grouped per day."""
        return {DAY_NAMES[day]: [b.as_dict() for b in self.for_day(day)] for day in range(7)}

    def timeline(self) -> tuple[str, ...]:
        """Return the preset for every minute of the week.

        Used to compare two programs semantically: the Toon may merge adjacent
        blocks with the same preset, which is still the same program.
        """
        grid: list[str | None] = [None] * MINUTES_PER_WEEK
        ordered = self.sorted_blocks
        for index, block in enumerate(ordered):
            following = ordered[(index + 1) % len(ordered)]
            delta = following.week_minute - block.week_minute
            if delta <= 0:
                delta += MINUTES_PER_WEEK
            for offset in range(delta):
                grid[(block.week_minute + offset) % MINUTES_PER_WEEK] = block.preset
        if any(preset is None for preset in grid):
            raise ToonFormatError("The week program does not cover the whole week")
        return tuple(preset for preset in grid if preset is not None)


def validate_blocks(blocks: Iterable[ProgramBlock]) -> tuple[ProgramBlock, ...]:
    """Validate and sort a set of program blocks."""
    ordered = sorted(blocks, key=lambda block: block.week_minute)
    if not ordered:
        raise ValueError("At least one program block is required")
    if len(ordered) > MAX_BLOCKS:
        raise ValueError(f"At most {MAX_BLOCKS} program blocks are supported")
    seen: set[tuple[int, int]] = set()
    for block in ordered:
        if not 0 <= block.day <= 6:
            raise ValueError(f"Invalid day: {block.day}")
        if not 0 <= block.minutes < MINUTES_PER_DAY:
            raise ValueError(f"Invalid time: {block.time}")
        if block.preset not in PRESET_IDS:
            raise ValueError(f"Invalid preset: {block.preset}")
        key = (block.day, block.minutes)
        if key in seen:
            raise ValueError(f"Duplicate block at {block.day_name} {block.time}")
        seen.add(key)
    return tuple(ordered)


def replace_day(
    program: WeekProgram, day: int, blocks: Iterable[ProgramBlock]
) -> list[ProgramBlock]:
    """Return the blocks of ``program`` with the blocks starting on ``day`` replaced."""
    merged = [block for block in program.sorted_blocks if block.day != day]
    merged.extend(blocks)
    return merged


def object_uuid(obj: dict[str, Any]) -> str | None:
    """Return the uuid of a ``getObjectConfig`` object, if it has one."""
    device = obj.get("device")
    if not isinstance(device, list):
        return None
    for node in device:
        if isinstance(node, dict) and "uuid" in node:
            value = node["uuid"]
            return value if isinstance(value, str) else None
    return None


def _single(node: Any) -> tuple[str, Any]:
    """Return the key/value pair of a single-key node."""
    if not isinstance(node, dict) or len(node) != 1:
        raise ToonFormatError(f"Expected a single-key node, got {node!r}")
    return next(iter(node.items()))


def _field(nodes: Any, name: str) -> Any:
    """Return the value of ``name`` from a list of single-key nodes."""
    if not isinstance(nodes, list):
        raise ToonFormatError(f"Expected a list for '{name}', got {nodes!r}")
    for node in nodes:
        key, value = _single(node)
        if key == name:
            return value
    raise ToonFormatError(f"Missing '{name}' in Toon object")


def _text_fields(node: list[Any]) -> dict[str, str]:
    """Flatten a list of single-key nodes into a dictionary."""
    result: dict[str, str] = {}
    for child in node:
        key, value = _single(child)
        result[key] = value
    return result


def parse_states(obj: dict[str, Any]) -> tuple[PresetState, ...]:
    """Parse a ``thermostatStates`` object."""
    device = obj.get("device")
    if not isinstance(device, list):
        raise ToonFormatError("The Toon object has no 'device' node")
    container = _field(device, "states")
    if not isinstance(container, list) or not container:
        raise ToonFormatError("The Toon object has no 'states' list")

    states: list[PresetState] = []
    for entry in container:
        fields = _text_fields(_field([entry], "state"))
        try:
            state_id = int(fields["id"])
            temperature = int(fields["tempValue"]) / 100
        except (KeyError, TypeError, ValueError) as err:
            raise ToonFormatError(f"Invalid preset state: {fields!r}") from err
        states.append(
            PresetState(
                state_id=state_id,
                temperature=temperature,
                dhw=fields.get("dhw", "1") == "1",
            )
        )
    if not states:
        raise ToonFormatError("The Toon returned no preset states")
    return tuple(sorted(states, key=lambda state: state.state_id))


def parse_program(obj: dict[str, Any]) -> WeekProgram:
    """Parse a ``thermostatProgram`` object."""
    device = obj.get("device")
    if not isinstance(device, list):
        raise ToonFormatError("The Toon object has no 'device' node")
    container = _field(device, "schedule")
    if not isinstance(container, list) or not container:
        raise ToonFormatError("The Toon object has no 'schedule' node")

    blocks: list[ProgramBlock] = []
    for entry in container:
        fields = _text_fields(_field([entry], "entry"))
        if fields.get("type") != "weekly_recurring":
            raise ToonFormatError(f"Unsupported program entry type: {fields.get('type')!r}")
        try:
            day = int(fields["startDayOfWeek"])
            minutes = int(fields["startHour"]) * 60 + int(fields["startMin"])
            preset = PRESET_STATES[int(fields["targetState"])]
        except (KeyError, TypeError, ValueError) as err:
            raise ToonFormatError(f"Invalid program entry: {fields!r}") from err
        blocks.append(ProgramBlock(day=day, minutes=minutes, preset=preset))

    return WeekProgram(tuple(blocks))


def build_program_object(
    template: dict[str, Any], blocks: Sequence[ProgramBlock]
) -> dict[str, Any]:
    """Return a copy of ``template`` with a new week program.

    Every other field of the object (uuid, type, visibility, ...) is preserved
    exactly as the Toon returned it.
    """
    ordered = validate_blocks(blocks)
    obj = _deep_copy(template)
    device = obj.get("device")
    if not isinstance(device, list):
        raise ToonFormatError("The Toon object has no 'device' node")
    container = _field(device, "schedule")
    if not isinstance(container, list) or not container:
        raise ToonFormatError("The Toon object has no 'schedule' node")

    entries: list[dict[str, Any]] = []
    for index, block in enumerate(ordered):
        following = ordered[(index + 1) % len(ordered)]
        entries.append(
            {
                "entry": [
                    {"type": "weekly_recurring"},
                    {"startMin": str(block.minute)},
                    {"startHour": str(block.hour)},
                    {"startDayOfWeek": str(block.day)},
                    {"targetState": str(PRESET_IDS[block.preset])},
                    {"endMin": str(following.minute)},
                    {"endHour": str(following.hour)},
                    {"endDayOfWeek": str(following.day)},
                ]
            }
        )

    _replace_field(device, "schedule", entries)
    return obj


def build_states_object(template: dict[str, Any], states: Sequence[PresetState]) -> dict[str, Any]:
    """Return a copy of ``template`` with new preset temperatures."""
    if not states:
        raise ValueError("At least one preset state is required")
    obj = _deep_copy(template)
    device = obj.get("device")
    if not isinstance(device, list):
        raise ToonFormatError("The Toon object has no 'device' node")
    container = _field(device, "states")
    if not isinstance(container, list) or not container:
        raise ToonFormatError("The Toon object has no 'states' node")

    entries: list[dict[str, Any]] = []
    for state in sorted(states, key=lambda item: item.state_id):
        entries.append(
            {
                "state": [
                    {"id": str(state.state_id)},
                    {"tempValue": str(round(state.temperature * 100))},
                    {"dhw": "1" if state.dhw else "0"},
                ]
            }
        )

    _replace_field(device, "states", entries)
    return obj


def _replace_field(nodes: list[Any], name: str, value: Any) -> None:
    """Replace the value of ``name`` in a list of single-key nodes."""
    for node in nodes:
        key, _ = _single(node)
        if key == name:
            node[key] = value
            return
    raise ToonFormatError(f"Missing '{name}' in Toon object")


def _xml_escape(value: str) -> str:
    """Escape XML special characters."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _xml_node(name: str, value: Any) -> str:
    """Render one node of a Toon object as XML."""
    if isinstance(value, list):
        inner = "".join(
            _xml_node(key, item_value) for item in value for key, item_value in item.items()
        )
        return f"<{name}>{inner}</{name}>"
    return f"<{name}>{_xml_escape(str(value))}</{name}>"


def to_xml(obj: dict[str, Any], revision: int) -> str:
    """Render a Toon object as the XML expected by ``setObjectConfig``.

    The Toon ignores a write when the ``packageRevision`` attribute does not
    increase, so the caller must pass a revision higher than the current one.
    """
    inner = "".join(_xml_node(key, value) for key, value in obj.items())
    return f'<Config packageRevision="{revision}">{inner}</Config>'


def _deep_copy(obj: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of a JSON-like object."""
    return copy.deepcopy(obj)
