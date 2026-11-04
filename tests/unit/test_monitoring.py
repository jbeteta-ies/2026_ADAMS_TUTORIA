"""Synthetic browser-free tests for independent multi-site monitoring."""

import json
from datetime import UTC, datetime, time

from adams_tutoria.config import SiteConfig
from adams_tutoria.monitoring import MonitorEventKind, MultiSiteMonitor


class Session:
    def __init__(self, *, fail_reload: bool = False) -> None:
        self.urls: list[str] = []
        self.closed = False
        self.fail_reload = fail_reload

    def reload(self, url: str, *, timeout_seconds: int) -> None:
        self.urls.append(url)
        assert timeout_seconds == 7
        if self.fail_reload:
            raise RuntimeError("synthetic reload failure")

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
    session = Session(fail_reload=True)
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


def test_login_and_reload_are_written_to_independent_safe_logs(tmp_path, monkeypatch) -> None:
    first = Session()
    second = Session()
    configured = [
        site("one", "https://example.invalid/one"),
        site("two", "https://example.invalid/two"),
    ]
    configured = [
        SiteConfig(
            item.id,
            item.provider,
            item.login_url,
            item.target_url,
            item.username,
            "synthetic-password-with-token-like-text",
            item.start_date,
            item.end_date,
            item.weekdays,
            item.start_time,
            item.end_time,
            item.timezone,
            item.interval_seconds,
            item.timeout_seconds,
            item.max_retries,
            tmp_path / f"{item.id}.log",
        )
        for item in configured
    ]
    adapters = {"one": Adapter(first), "two": Adapter(second)}
    monkeypatch.setattr("adams_tutoria.monitoring.adapter_for_site", lambda item: adapters[item.id])
    monitor = MultiSiteMonitor(configured, browser_factory=lambda: object())

    monitor.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC), monotonic=0)
    monitor.tick(datetime(2026, 1, 5, 9, 0, 1, tzinfo=UTC), monotonic=10)

    for item in configured:
        records = [json.loads(line) for line in item.log_file.read_text().splitlines()]
        assert [record["action"] for record in records] == ["login", "reload"]
        assert all(
            set(record) == {"timestamp", "site_id", "provider", "action", "result"}
            for record in records
        )
        text = item.log_file.read_text()
        assert "synthetic-password-with-token-like-text" not in text
        assert "cookie" not in text.lower()
        assert "<html" not in text.lower()


def test_logs_exclude_tokens_headers_and_synthetic_personal_data(tmp_path) -> None:
    configured = SiteConfig(
        "safe-site",
        "SYNTHETIC",
        "https://example.invalid/login",
        "https://example.invalid/target",
        "alumno.001@example.invalid",
        "synthetic-password-123",
        start_time=time(9),
        end_time=time(10),
        weekdays=("MONDAY",),
        interval_seconds=10,
        timeout_seconds=7,
        max_retries=1,
        log_file=tmp_path / "safe-site.log",
    )

    from adams_tutoria.site_logging import SiteLogWriter

    sensitive_values = (
        "Bearer synthetic-token-abc",
        "Cookie: session=synthetic-cookie-value",
        "Authorization: Basic synthetic-header-value",
        "<html><body>synthetic page</body></html>",
        "Alumna Sintética",
        "alumna.sintetica@example.invalid",
    )
    assert SiteLogWriter(configured).write(
        action="login",
        result="error",
        error=" | ".join(sensitive_values),
    )

    text = configured.log_file.read_text()
    assert '"error":"operation failed"' in text
    for value in sensitive_values:
        assert value not in text
    assert configured.password not in text
    assert configured.username not in text


def test_log_write_failure_is_reported_without_stopping_other_sites(monkeypatch, tmp_path) -> None:
    sessions = {"one": Session(), "two": Session()}
    configured = [
        site("one", "https://example.invalid/one"),
        site("two", "https://example.invalid/two"),
    ]
    monkeypatch.setattr(
        "adams_tutoria.monitoring.adapter_for_site", lambda item: Adapter(sessions[item.id])
    )
    writers = {}

    class BrokenWriter:
        def write(self, **kwargs: object) -> bool:
            del kwargs
            raise OSError("private diagnostic")

    def writer_factory(item: SiteConfig):
        if item.id == "one":
            return BrokenWriter()
        from adams_tutoria.site_logging import SiteLogWriter

        writers[item.id] = item.log_file
        return SiteLogWriter(item)

    configured[1] = SiteConfig(
        configured[1].id,
        configured[1].provider,
        configured[1].login_url,
        configured[1].target_url,
        configured[1].username,
        configured[1].password,
        configured[1].start_date,
        configured[1].end_date,
        configured[1].weekdays,
        configured[1].start_time,
        configured[1].end_time,
        configured[1].timezone,
        configured[1].interval_seconds,
        configured[1].timeout_seconds,
        configured[1].max_retries,
        tmp_path / "two.log",
    )
    events = MultiSiteMonitor(
        configured, browser_factory=lambda: object(), log_writer_factory=writer_factory
    ).tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC), monotonic=0)
    assert ("one", MonitorEventKind.ERROR) in {(event.site_id, event.kind) for event in events}
    assert ("two", MonitorEventKind.LOGIN) in {(event.site_id, event.kind) for event in events}


def test_reload_log_failure_keeps_reload_failure_and_safe_logging_diagnostic(
    monkeypatch,
) -> None:
    session = Session()

    class ReloadLogFailure:
        calls = 0

        def write(self, *, action: str, result: str, error: str | None = None) -> bool:
            self.calls += 1
            if self.calls == 1:
                assert action == "login"
                assert result == "success"
                assert error is None
                return True
            assert action == "reload"
            assert result == "success"
            assert error is None
            raise OSError("synthetic private logging failure")

    monkeypatch.setattr("adams_tutoria.monitoring.adapter_for_site", lambda _: Adapter(session))
    monitor = MultiSiteMonitor(
        [site("one", "https://example.invalid/one")],
        browser_factory=lambda: object(),
        log_writer_factory=lambda _: ReloadLogFailure(),
    )
    at_start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)

    monitor.tick(at_start, monotonic=0)
    events = monitor.tick(at_start, monotonic=10)

    assert [(event.kind, event.message) for event in events] == [
        (MonitorEventKind.RELOAD, ""),
        (MonitorEventKind.ERROR, "Registro local no disponible."),
    ]
    assert session.closed
