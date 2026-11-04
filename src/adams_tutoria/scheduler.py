"""Independent, provider-neutral scheduling of configured sites.

The scheduler only produces state-transition events.  It does not log in,
navigate, or perform work for a site.  The start is inclusive and the end is
exclusive.  A window may cross midnight; its after-midnight portion belongs to
the weekday on which the window started.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from time import sleep
from zoneinfo import ZoneInfo

from adams_tutoria.config import SiteConfig


class ScheduleState(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    INVALID = "invalid"


class ScheduleEventKind(StrEnum):
    ENTER = "enter"
    EXIT = "exit"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ScheduleEvent:
    """A safe, site-scoped transition emitted by the scheduler."""

    site_id: str
    kind: ScheduleEventKind
    at: datetime
    message: str = ""


class SiteSchedule:
    """Evaluate one site's window without retaining operational credentials."""

    def __init__(self, site: SiteConfig) -> None:
        self.site_id = site.id
        self._start_date = site.start_date
        self._end_date = site.end_date
        self._weekdays = frozenset(site.weekdays)
        self._start_time = site.start_time
        self._end_time = site.end_time
        if (
            self._start_time.tzinfo is not None
            or self._start_time.utcoffset() is not None
            or self._end_time.tzinfo is not None
            or self._end_time.utcoffset() is not None
        ):
            raise ValueError("schedule times must not include a timezone")
        try:
            self._timezone = ZoneInfo(site.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("site timezone is invalid") from exc
        if self._start_time == self._end_time:
            raise ValueError("schedule start_time and end_time must differ")
        if self._start_date and self._end_date and self._end_date < self._start_date:
            raise ValueError("schedule end_date must not precede start_date")

    def state_at(self, now: datetime) -> ScheduleState:
        """Return the state at an aware instant, converted to the site's zone."""

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("scheduler clock must return an aware datetime")
        local = now.astimezone(self._timezone)
        local_date = local.date()
        local_time = local.time()
        overnight = self._start_time > self._end_time
        owner_date = (
            local_date.fromordinal(local_date.toordinal() - 1)
            if overnight and local_time < self._end_time
            else local_date
        )
        if self._start_date and owner_date < self._start_date:
            return ScheduleState.INACTIVE
        if self._end_date and owner_date > self._end_date:
            return ScheduleState.INACTIVE
        weekday_name = (
            "MONDAY",
            "TUESDAY",
            "WEDNESDAY",
            "THURSDAY",
            "FRIDAY",
            "SATURDAY",
            "SUNDAY",
        )[local.weekday()]
        if self._start_time < self._end_time:
            active = (
                weekday_name in self._weekdays and self._start_time <= local_time < self._end_time
            )
        else:
            # At or after midnight, inspect the preceding local date: that is
            # the date whose weekday owns the overnight window.
            previous_date = owner_date
            previous_weekday = (
                "MONDAY",
                "TUESDAY",
                "WEDNESDAY",
                "THURSDAY",
                "FRIDAY",
                "SATURDAY",
                "SUNDAY",
            )[previous_date.weekday()]
            active = (weekday_name in self._weekdays and local_time >= self._start_time) or (
                previous_weekday in self._weekdays and local_time < self._end_time
            )
        return ScheduleState.ACTIVE if active else ScheduleState.INACTIVE


@dataclass
class _SiteRuntime:
    schedule: SiteSchedule
    state: ScheduleState | None = None
    invalid_message: str | None = None


class SiteScheduler:
    """Continuously evaluate independent site windows using injected time."""

    def __init__(
        self,
        sites: Iterable[SiteConfig],
        *,
        poll_seconds: float = 60.0,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.poll_seconds = poll_seconds
        self._sites: list[_SiteRuntime] = []
        for site in sites:
            try:
                schedule = SiteSchedule(site)
            except (TypeError, ValueError) as exc:
                # Invalid sites are permanently inactive and isolated from the
                # valid sites.  Do not retain or expose the invalid input.
                self._sites.append(
                    _SiteRuntime(
                        SiteSchedule.__new__(SiteSchedule),
                        ScheduleState.INVALID,
                        str(exc),
                    )
                )
                self._sites[-1].schedule.site_id = getattr(site, "id", "unknown")
            else:
                self._sites.append(_SiteRuntime(schedule))

    def tick(self, now: datetime) -> tuple[ScheduleEvent, ...]:
        """Evaluate every site once and return only state transitions.

        The initial evaluation emits ``ENTER`` for an active site, making a
        process restart deterministic and safe.  Invalid sites emit one
        ``INVALID`` event and never become active.
        """

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("scheduler clock must return an aware datetime")
        events: list[ScheduleEvent] = []
        for runtime in self._sites:
            site_id = runtime.schedule.site_id
            if runtime.invalid_message is not None:
                if runtime.state is ScheduleState.INVALID:
                    events.append(
                        ScheduleEvent(
                            site_id, ScheduleEventKind.INVALID, now, runtime.invalid_message
                        )
                    )
                    runtime.state = ScheduleState.INACTIVE
                continue
            state = runtime.schedule.state_at(now)
            previous = runtime.state
            runtime.state = state
            if state is ScheduleState.ACTIVE and previous is not ScheduleState.ACTIVE:
                events.append(ScheduleEvent(site_id, ScheduleEventKind.ENTER, now))
            elif state is ScheduleState.INACTIVE and previous is ScheduleState.ACTIVE:
                events.append(ScheduleEvent(site_id, ScheduleEventKind.EXIT, now))
        return tuple(events)

    def run_forever(
        self,
        *,
        clock: Callable[[], datetime] = datetime.now,
        wait: Callable[[float], None] = sleep,
        on_events: Callable[[tuple[ScheduleEvent, ...]], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        """Run until ``should_stop`` says so; dependencies are injectable for tests."""

        stop = should_stop or (lambda: False)
        while not stop():
            events = self.tick(clock())
            if on_events is not None and events:
                on_events(events)
            wait(self.poll_seconds)


__all__ = ["ScheduleEvent", "ScheduleEventKind", "ScheduleState", "SiteSchedule", "SiteScheduler"]
