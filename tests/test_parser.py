"""Tests for the pure parsing layer of the Toon Program integration.

The parser has no Home Assistant or aiohttp imports, so these tests run with a
plain Python interpreter::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "toon_program"
if "toon_program" not in sys.modules:
    # Load the parser as a package without executing the integration's
    # __init__.py, which imports Home Assistant.
    package = types.ModuleType("toon_program")
    package.__path__ = [str(COMPONENT)]  # type: ignore[attr-defined]
    sys.modules["toon_program"] = package

from toon_program import parser  # noqa: E402
from toon_program.parser import ProgramBlock, ToonFormatError, WeekProgram  # noqa: E402

STATES_OBJECT = {
    "device": [
        {
            "states": [
                {"state": [{"id": "0"}, {"tempValue": "1900"}, {"dhw": "1"}]},
                {"state": [{"id": "1"}, {"tempValue": "1800"}, {"dhw": "1"}]},
                {"state": [{"id": "2"}, {"tempValue": "1600"}, {"dhw": "1"}]},
                {"state": [{"id": "3"}, {"tempValue": "1600"}, {"dhw": "1"}]},
                {"state": [{"id": "4"}, {"tempValue": "600"}, {"dhw": "1"}]},
            ]
        },
        {"package": "happ_thermstat"},
        {"uuid": "00000000-0000-4000-8000-000000000001"},
        {"type": "states"},
        {"name": "thermostatStates"},
        {"internalAddress": "thermostatStates"},
        {"visibility": "0"},
        {"statesSaved": "1"},
    ]
}

PROGRAM_OBJECT = {
    "device": [
        {
            "schedule": [
                {
                    "entry": [
                        {"type": "weekly_recurring"},
                        {"startMin": "30"},
                        {"startHour": "7"},
                        {"startDayOfWeek": "0"},
                        {"targetState": "1"},
                        {"endMin": "0"},
                        {"endHour": "8"},
                        {"endDayOfWeek": "0"},
                    ]
                },
                {
                    "entry": [
                        {"type": "weekly_recurring"},
                        {"startMin": "0"},
                        {"startHour": "8"},
                        {"startDayOfWeek": "0"},
                        {"targetState": "3"},
                        {"endMin": "0"},
                        {"endHour": "22"},
                        {"endDayOfWeek": "0"},
                    ]
                },
                {
                    "entry": [
                        {"type": "weekly_recurring"},
                        {"startMin": "0"},
                        {"startHour": "22"},
                        {"startDayOfWeek": "0"},
                        {"targetState": "2"},
                        {"endMin": "30"},
                        {"endHour": "7"},
                        {"endDayOfWeek": "0"},
                    ]
                },
            ]
        },
        {"package": "happ_thermstat"},
        {"uuid": "00000000-0000-4000-8000-000000000002"},
        {"type": "program"},
        {"internalAddress": "thermostatProgram"},
        {"visibility": "1"},
    ]
}


class ParseStatesTest(unittest.TestCase):
    """thermostatStates is stored in 1/100 degrees."""

    def test_presets_are_parsed(self) -> None:
        states = parser.parse_states(STATES_OBJECT)
        self.assertEqual(
            [state.name for state in states],
            ["comfort", "home", "sleep", "away", "holiday"],
        )
        self.assertEqual(states[0].temperature, 19.0)
        self.assertEqual(states[4].temperature, 6.0)
        self.assertTrue(all(state.dhw for state in states))


class ParseProgramTest(unittest.TestCase):
    """thermostatProgram is stored as a flat list of schedule entries."""

    def setUp(self) -> None:
        self.program = parser.parse_program(PROGRAM_OBJECT)

    def test_blocks_are_parsed_in_weekly_order(self) -> None:
        self.assertEqual(len(self.program.blocks), 3)
        self.assertEqual(
            self.program.sorted_blocks[0], ProgramBlock(day=0, minutes=450, preset="home")
        )
        self.assertEqual(
            self.program.sorted_blocks[1], ProgramBlock(day=0, minutes=480, preset="away")
        )
        self.assertEqual(
            self.program.sorted_blocks[2], ProgramBlock(day=0, minutes=1320, preset="sleep")
        )

    def test_block_durations_wrap_the_week(self) -> None:
        self.assertEqual(self.program.duration(self.program.sorted_blocks[0]), 30)
        self.assertEqual(self.program.duration(self.program.sorted_blocks[1]), 14 * 60)
        # Sunday 22:00 until Sunday 07:30 is 9.5 hours, through the rest of the week.
        self.assertEqual(
            self.program.duration(self.program.sorted_blocks[2]),
            6 * 24 * 60 + 9 * 60 + 30,
        )

    def test_timeline_covers_the_whole_week(self) -> None:
        timeline = self.program.timeline()
        self.assertEqual(len(timeline), 7 * 24 * 60)
        # Sunday 00:00 is still covered by the Sunday 22:00 block of the previous week.
        self.assertEqual(timeline[0], "sleep")
        self.assertEqual(timeline[7 * 60 + 30], "home")


class RoundTripTest(unittest.TestCase):
    """An unmodified object must be written back byte for byte."""

    def test_program_roundtrip_is_identical(self) -> None:
        program = parser.parse_program(PROGRAM_OBJECT)
        rebuilt = parser.build_program_object(PROGRAM_OBJECT, program.blocks)
        self.assertEqual(rebuilt, PROGRAM_OBJECT)
        self.assertEqual(json.dumps(rebuilt), json.dumps(PROGRAM_OBJECT))

    def test_states_roundtrip_is_identical(self) -> None:
        states = parser.parse_states(STATES_OBJECT)
        rebuilt = parser.build_states_object(STATES_OBJECT, states)
        self.assertEqual(rebuilt, STATES_OBJECT)


class EditingTest(unittest.TestCase):
    """Edits touch the schedule or the temperatures, never the metadata."""

    def test_program_edit_keeps_metadata(self) -> None:
        program = parser.parse_program(PROGRAM_OBJECT)
        blocks = list(program.sorted_blocks)
        blocks[0] = ProgramBlock(day=0, minutes=450, preset="comfort")
        rebuilt = parser.build_program_object(PROGRAM_OBJECT, blocks)

        self.assertEqual(parser.parse_program(rebuilt).sorted_blocks[0].preset, "comfort")
        self.assertEqual(rebuilt["device"][1:], PROGRAM_OBJECT["device"][1:])

    def test_states_edit_uses_hundredths(self) -> None:
        states = parser.parse_states(STATES_OBJECT)
        updated = tuple(
            state.__class__(
                state_id=state.state_id,
                temperature=21.5 if state.state_id == 0 else state.temperature,
                dhw=state.dhw,
            )
            for state in states
        )
        rebuilt = parser.build_states_object(STATES_OBJECT, updated)

        self.assertEqual(parser.parse_states(rebuilt)[0].temperature, 21.5)
        self.assertEqual(rebuilt["device"][1:], STATES_OBJECT["device"][1:])

    def test_blocks_are_sorted_before_writing(self) -> None:
        blocks = [
            ProgramBlock(day=2, minutes=600, preset="home"),
            ProgramBlock(day=0, minutes=450, preset="comfort"),
        ]
        rebuilt = parser.build_program_object(PROGRAM_OBJECT, blocks)
        reparsed = parser.parse_program(rebuilt)

        self.assertEqual([block.day for block in reparsed.sorted_blocks], [0, 2])
        self.assertEqual(reparsed.duration(reparsed.sorted_blocks[1]), 4 * 24 * 60 + 1290)


class ValidationTest(unittest.TestCase):
    """Invalid input is rejected before anything is written."""

    def test_validate_blocks_rejects_invalid_input(self) -> None:
        for blocks in (
            [],
            [ProgramBlock(7, 600, "home")],
            [ProgramBlock(0, 1440, "home")],
            [ProgramBlock(0, 600, "onzin")],
            [ProgramBlock(0, 600, "home"), ProgramBlock(0, 600, "away")],
        ):
            with self.subTest(blocks=blocks), self.assertRaises(ValueError):
                parser.validate_blocks(blocks)

    def test_unknown_preset_is_rejected(self) -> None:
        broken = json.loads(json.dumps(PROGRAM_OBJECT))
        broken["device"][0]["schedule"][0]["entry"][4]["targetState"] = "9"
        with self.assertRaises(ToonFormatError):
            parser.parse_program(broken)

    def test_week_program_requires_blocks(self) -> None:
        with self.assertRaises(ToonFormatError):
            WeekProgram(())


if __name__ == "__main__":
    unittest.main()
