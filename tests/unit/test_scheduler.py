"""Synthetic, controlled-clock tests for independent site scheduling."""

from datetime import UTC, date, datetime, time

from adams_tutoria.config import SiteConfig
from adams_tutoria.scheduler import (
    ScheduleEventKind,
    ScheduleState,
    SiteSchedule,
    SiteScheduler,
    WindowPhase,
)


def _site(site_id: str, **overrides: object) -> SiteConfig:
    values: dict[str, object] = {
        "id": site_id,
        "provider": "SYNTHETIC",
        "login_url": "https://example.invalid/login",
        "target_url": "https://example.invalid/target",
        "username": "synthetic-user",
        "password": "synthetic-password",
        "timezone": "UTC",
        "start_time": time(9),
        "end_time": time(10),
        "weekdays": ("MONDAY",),
    }
    values.update(overrides)
    return SiteConfig(**values)  # type: ignore[arg-type]


def test_boundaries_dates_timezone_and_restart_are_deterministic() -> None:
    scheduler = SiteScheduler(
        [
            _site(
                "madrid",
                timezone="Europe/Madrid",
                start_date=date(2026, 1, 5),
                end_date=date(2026, 1, 5),
            )
        ]
    )
    at_start = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    assert scheduler.tick(at_start)[0].kind is ScheduleEventKind.ENTER
    assert scheduler.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.EXIT
    assert scheduler.tick(datetime(2026, 1, 6, 8, 0, tzinfo=UTC)) == ()


def test_sites_are_independent() -> None:
    scheduler = SiteScheduler(
        [_site("active"), _site("later", start_time=time(11), end_time=time(12))]
    )
    events = scheduler.tick(datetime(2026, 1, 5, 9, 30, tzinfo=UTC))
    assert [(event.site_id, event.kind) for event in events] == [
        ("active", ScheduleEventKind.ENTER)
    ]


def test_invalid_site_does_not_block_valid_site() -> None:
    invalid = _site("broken", timezone="Not/AZone")
    scheduler = SiteScheduler([invalid, _site("valid")])
    events = scheduler.tick(datetime(2026, 1, 5, 9, 30, tzinfo=UTC))
    assert events[0].kind is ScheduleEventKind.INVALID
    assert events[1].kind is ScheduleEventKind.ENTER
    assert scheduler.tick(datetime(2026, 1, 5, 9, 31, tzinfo=UTC)) == ()


def test_timezone_embedded_in_site_time_is_isolated_without_exposing_values() -> None:
    invalid = _site("broken-time", start_time=time(9, tzinfo=UTC))
    scheduler = SiteScheduler([invalid, _site("valid")])

    events = scheduler.tick(datetime(2026, 1, 5, 9, 30, tzinfo=UTC))

    assert [(event.site_id, event.kind) for event in events] == [
        ("broken-time", ScheduleEventKind.INVALID),
        ("valid", ScheduleEventKind.ENTER),
    ]
    assert "09:00" not in events[0].message
    assert scheduler.tick(datetime(2026, 1, 5, 9, 31, tzinfo=UTC)) == ()


def test_run_forever_uses_injected_wait_and_clock() -> None:
    scheduler = SiteScheduler([_site("demo")], poll_seconds=0.25)
    calls = 0
    waits: list[float] = []

    def stop() -> bool:
        return calls >= 2

    def clock() -> datetime:
        return datetime(2026, 1, 5, 9, 30, tzinfo=UTC)

    def wait(seconds: float) -> None:
        nonlocal calls
        waits.append(seconds)
        calls += 1

    scheduler.run_forever(clock=clock, wait=wait, should_stop=stop)
    assert waits == [0.25, 0.25]


def test_naive_clock_is_rejected() -> None:
    scheduler = SiteScheduler([_site("demo")])
    try:
        scheduler.tick(datetime(2026, 1, 5, 9, 30))
    except ValueError as error:
        assert "aware" in str(error)
    else:
        raise AssertionError("naive clock must be rejected")


def test_schedule_state_is_available_for_direct_evaluation() -> None:
    from adams_tutoria.scheduler import SiteSchedule

    schedule = SiteSchedule(_site("demo"))
    assert schedule.state_at(datetime(2026, 1, 5, 9, 30, tzinfo=UTC)) is ScheduleState.ACTIVE


def test_run_window_phase_is_before_active_and_after_with_exact_close() -> None:
    schedule = SiteSchedule(_site("demo"))
    assert schedule.phase_at(datetime(2026, 1, 5, 8, 59, tzinfo=UTC)) is WindowPhase.BEFORE
    assert schedule.phase_at(datetime(2026, 1, 5, 9, 0, tzinfo=UTC)) is WindowPhase.ACTIVE
    assert schedule.phase_at(datetime(2026, 1, 5, 10, 0, tzinfo=UTC)) is WindowPhase.AFTER


def test_run_window_phase_handles_overnight_window_without_second_start() -> None:
    schedule = SiteSchedule(
        _site("night", start_time=time(22), end_time=time(2), weekdays=("MONDAY",))
    )
    assert schedule.phase_at(datetime(2026, 1, 5, 21, 59, tzinfo=UTC)) is WindowPhase.BEFORE
    assert schedule.phase_at(datetime(2026, 1, 5, 22, tzinfo=UTC)) is WindowPhase.ACTIVE
    assert schedule.phase_at(datetime(2026, 1, 6, 1, 59, tzinfo=UTC)) is WindowPhase.ACTIVE
    assert schedule.phase_at(datetime(2026, 1, 6, 2, tzinfo=UTC)) is WindowPhase.AFTER
    assert schedule.phase_at(datetime(2026, 1, 6, 22, tzinfo=UTC)) is WindowPhase.BEFORE


def test_overnight_window_uses_start_weekday_and_exclusive_end() -> None:
    scheduler = SiteScheduler(
        [_site("night", start_time=time(22), end_time=time(2), weekdays=("MONDAY",))]
    )
    assert (
        scheduler.tick(datetime(2026, 1, 5, 22, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.ENTER
    )
    assert scheduler.tick(datetime(2026, 1, 6, 1, 59, tzinfo=UTC)) == ()
    assert scheduler.tick(datetime(2026, 1, 6, 2, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.EXIT


def test_overnight_window_does_not_start_on_following_weekday() -> None:
    scheduler = SiteScheduler(
        [_site("night", start_time=time(22), end_time=time(2), weekdays=("MONDAY",))]
    )
    assert scheduler.tick(datetime(2026, 1, 6, 22, 0, tzinfo=UTC)) == ()
    assert scheduler.tick(datetime(2026, 1, 7, 1, 59, tzinfo=UTC)) == ()


def test_overnight_end_date_includes_its_after_midnight_segment() -> None:
    scheduler = SiteScheduler(
        [
            _site(
                "last-night",
                start_date=date(2026, 1, 5),
                end_date=date(2026, 1, 5),
                start_time=time(22),
                end_time=time(2),
                weekdays=("MONDAY",),
            )
        ]
    )
    assert (
        scheduler.tick(datetime(2026, 1, 6, 1, 59, tzinfo=UTC))[0].kind is ScheduleEventKind.ENTER
    )
    assert scheduler.tick(datetime(2026, 1, 6, 2, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.EXIT


def test_overnight_boundary_and_date_range_are_explicit() -> None:
    scheduler = SiteScheduler(
        [
            _site(
                "night",
                start_date=date(2026, 1, 5),
                end_date=date(2026, 1, 5),
                start_time=time(22, 50),
                end_time=time(1),
                weekdays=("MONDAY",),
            )
        ]
    )
    start_events = scheduler.tick(datetime(2026, 1, 5, 22, 50, tzinfo=UTC))
    assert start_events[0].kind is ScheduleEventKind.ENTER
    assert scheduler.tick(datetime(2026, 1, 6, 0, 0, tzinfo=UTC)) == ()
    assert scheduler.is_active("night", datetime(2026, 1, 6, 0, 59, tzinfo=UTC))
    assert not scheduler.is_active("night", datetime(2026, 1, 6, 1, 0, tzinfo=UTC))


def test_two_consecutive_enabled_days_have_one_window_each() -> None:
    scheduler = SiteScheduler(
        [_site("weekday", weekdays=("MONDAY", "TUESDAY"), start_time=time(9), end_time=time(10))]
    )

    assert scheduler.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.ENTER
    assert scheduler.tick(datetime(2026, 1, 5, 10, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.EXIT
    assert scheduler.tick(datetime(2026, 1, 6, 9, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.ENTER
    assert scheduler.tick(datetime(2026, 1, 6, 10, 0, tzinfo=UTC))[0].kind is ScheduleEventKind.EXIT


def test_weekend_is_not_allowed_when_only_weekdays_are_enabled() -> None:
    scheduler = SiteScheduler([_site("weekday", weekdays=("MONDAY", "FRIDAY"))])

    assert scheduler.tick(datetime(2026, 1, 10, 9, 0, tzinfo=UTC)) == ()  # Saturday
    assert scheduler.tick(datetime(2026, 1, 11, 9, 0, tzinfo=UTC)) == ()  # Sunday
