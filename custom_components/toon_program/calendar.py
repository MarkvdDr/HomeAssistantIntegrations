"""Calendar view of the Toon week program."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import PRESET_LABELS
from .coordinator import ToonProgramConfigEntry, ToonProgramCoordinator, toon_day
from .entity import ToonProgramEntity
from .parser import ProgramBlock

PARALLEL_UPDATES = 0

# A calendar view never needs more than this; it protects against a client
# asking for a range of centuries.
_MAX_RANGE_DAYS = 400


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ToonProgramConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the week program calendar."""
    async_add_entities([ToonWeekProgramCalendar(entry.runtime_data, entry)])


class ToonWeekProgramCalendar(ToonProgramEntity, CalendarEntity):
    """The Toon week program as a weekly recurring calendar."""

    _attr_translation_key = "week_program"
    _attr_icon = "mdi:calendar-week"

    def __init__(self, coordinator: ToonProgramCoordinator, entry: ToonProgramConfigEntry) -> None:
        """Initialise the calendar."""
        super().__init__(coordinator, entry, "week_program_calendar")

    def _label(self, preset: str) -> str:
        """Return the display name of a preset in the Home Assistant language."""
        labels = PRESET_LABELS.get(self.hass.config.language.split("-")[0], PRESET_LABELS["en"])
        return labels.get(preset, preset.title())

    def _build_event(self, block: ProgramBlock, day: date) -> CalendarEvent:
        """Build the calendar event of ``block`` as it occurs on ``day``."""
        coordinator = self.coordinator
        program = coordinator.data.program
        tz = coordinator.tz
        start = datetime.combine(day, time(block.hour, block.minute), tzinfo=tz)
        # Add the duration to the wall clock, so the block ends at the clock
        # time the Toon uses even when a daylight-saving change is in between.
        end_wall = datetime.combine(day, time(block.hour, block.minute)) + timedelta(
            minutes=program.duration(block)
        )
        end = end_wall.replace(tzinfo=tz)
        temperature = coordinator.data.temperature_for(block.preset)
        summary = self._label(block.preset)
        if temperature is not None:
            summary = f"{summary} ({temperature:g} °C)"
        return CalendarEvent(
            start=start,
            end=end,
            summary=summary,
            description=f"Toon: {block.preset} {block.time}",
            uid=f"toon-program-{block.day}-{block.minutes}-{day.isoformat()}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the block that is active right now."""
        coordinator = self.coordinator
        if coordinator.data is None:
            return None
        now = coordinator.now()
        block = coordinator.active_block(now)
        if block is None:
            return None
        # The active block started today or, at most, six days ago.
        days_back = (toon_day(now) - block.day) % 7
        if days_back == 0 and block.minutes > now.hour * 60 + now.minute:
            days_back = 7
        return self._build_event(block, now.date() - timedelta(days=days_back))

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the program blocks between two moments."""
        coordinator = self.coordinator
        if coordinator.data is None:
            return []
        program = coordinator.data.program
        tz = coordinator.tz
        start = dt_util.as_local(start_date).astimezone(tz)
        end = dt_util.as_local(end_date).astimezone(tz)

        events: list[CalendarEvent] = []
        # Start a week early: the last block of the previous week reaches into
        # the first days of the requested range.
        day = start.date() - timedelta(days=7)
        last = min(end.date(), start.date() + timedelta(days=_MAX_RANGE_DAYS))
        while day <= last:
            for block in program.for_day(toon_day(datetime.combine(day, time()))):
                event = self._build_event(block, day)
                if event.end > start and event.start < end:
                    events.append(event)
            day += timedelta(days=1)

        events.sort(key=lambda item: item.start)
        return events
