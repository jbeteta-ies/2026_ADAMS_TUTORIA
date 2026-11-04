"""Synthetic browser-free tests for independent multi-site monitoring."""

from datetime import UTC, datetime, time

from adams_tutoria.config import SiteConfig
from adams_tutoria.monitoring import MonitorEventKind, MultiSiteMonitor


class Session:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.closed = False

    def reload(self, url: str, *, timeout_seconds: int) -> None:
        self.urls.append(url)
        assert timeout_seconds == 7

    def close(self) -> None:
        self.closed = True


class Adapter:
    def __init__(self, session: Session | None) -> None:
        self.session = session

    def login_session(
        self, request: object, *, browser_api: object
    ) -> tuple[object, Session | None]:
        del request, browser_api
        return type(
            "Outcome", (), {"status": type("Status", (), {"value": "success"})()}
        )(), self.session


class RetryingAdapter:
    def __init__(self, failures: int, session: Session) -> None:
        self.failures = failures
        self.calls = 0
        self.session = session

    def login_session(
        self, request: object, *, browser_api: object
    ) -> tuple[object, Session | None]:
        del request, browser_api
        self.calls += 1
        status = "failed" if self.calls <= self.failures else "success"
        return type("Outcome", (), {"status": type("Status", (), {"value": status})()})(), (
            self.session if status == "success" else None
        )


def site(site_id: str, target: str, *, max_retries: int = 1) -> SiteConfig:
    return SiteConfig(
        site_id,
        "SYNTHETIC",
        "https://example.invalid/login",
        target,
        "synthetic-user",
        "synthetic-password",
        start_time=time(9),
        end_time=time(10),
        weekdays=("MONDAY",),
        interval_seconds=10,
        timeout_seconds=7,
        max_retries=max_retries,
    )


def test_login_reload_exit_and_site_isolation(monkeypatch) -> None:
    first = Session()
    second = Session()
    adapters = {"one": Adapter(first), "two": Adapter(second)}
    monkeypatch.setattr(
        "adams_tutoria.monitoring.adapter_for_site", lambda configured: adapters[configured.id]
    )
    monitor = MultiSiteMonitor(
        [site("one", "https://example.invalid/one"), site("two", "https://example.invalid/two")],
        browser_factory=lambda: object(),
    )
    at_start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)

    events = monitor.tick(at_start, monotonic=0)
    assert {event.site_id for event in events if event.kind is MonitorEventKind.LOGIN} == {
        "one",
        "two",
    }
    assert monitor.tick(at_start, monotonic=10)[0].kind is MonitorEventKind.RELOAD
    assert first.urls == ["https://example.invalid/one"]
    assert second.urls == ["https://example.invalid/two"]

    exit_events = monitor.tick(datetime(2026, 1, 5, 10, 0, tzinfo=UTC), monotonic=11)
    assert {event.site_id for event in exit_events} == {"one", "two"}
    assert first.closed and second.closed


def test_close_is_idempotent(monkeypatch) -> None:
    session = Session()
    monkeypatch.setattr(
        "adams_tutoria.monitoring.adapter_for_site", lambda configured: Adapter(session)
    )
    monitor = MultiSiteMonitor(
        [site("one", "https://example.invalid/one")], browser_factory=lambda: object()
    )
    monitor.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC), monotonic=0)
    monitor.close()
    monitor.close()
    assert session.closed


def test_one_shot_site_iterable_is_used_by_scheduler_and_runtimes(monkeypatch) -> None:
    configured = [site("one", "https://example.invalid/one")]
    session = Session()
    monkeypatch.setattr("adams_tutoria.monitoring.adapter_for_site", lambda _: Adapter(session))
    monitor = MultiSiteMonitor((item for item in configured), browser_factory=lambda: object())

    events = monitor.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC), monotonic=0)

    assert [(event.site_id, event.kind) for event in events] == [("one", MonitorEventKind.LOGIN)]


def test_max_retries_is_number_of_retries_after_first_attempt(monkeypatch) -> None:
    session = Session()
    adapter = RetryingAdapter(failures=2, session=session)
    monkeypatch.setattr("adams_tutoria.monitoring.adapter_for_site", lambda _: adapter)
    monitor = MultiSiteMonitor(
        [site("one", "https://example.invalid/one", max_retries=2)],
        browser_factory=lambda: object(),
    )

    events = monitor.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC), monotonic=0)

    assert adapter.calls == 2 + 1
    assert events[0].kind is MonitorEventKind.LOGIN


def test_unknown_provider_isolated_from_other_sites(monkeypatch) -> None:
    first = Session()
    adapters = {"one": Adapter(first)}

    def resolve(configured: SiteConfig) -> Adapter:
        if configured.id == "two":
            raise ValueError("unknown provider")
        return adapters[configured.id]

    monkeypatch.setattr("adams_tutoria.monitoring.adapter_for_site", resolve)
    monitor = MultiSiteMonitor(
        [site("one", "https://example.invalid/one"), site("two", "https://example.invalid/two")],
        browser_factory=lambda: object(),
    )

    events = monitor.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC), monotonic=0)

    assert {event.site_id: event.kind for event in events} == {
        "one": MonitorEventKind.LOGIN,
        "two": MonitorEventKind.ERROR,
    }
