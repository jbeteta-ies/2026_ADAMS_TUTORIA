"""Synthetic browser-free tests for independent multi-site monitoring."""

import json
from datetime import UTC, datetime, time

from adams_tutoria.config import SiteConfig
from adams_tutoria.declarative_navigation import ExpectedResult, NavigationPlan, NavigationStep
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


def test_multisite_monitor_emits_navigation_success_after_login_and_reload(
    monkeypatch, tmp_path
) -> None:
    class Response:
        status = 200

    class Page:
        url = "https://example.invalid/target"
        body = "Synthetic monitoring target"

        def __init__(self) -> None:
            self.navigation_calls = 0

        def locator(self, selector: str):
            assert selector == "body"
            return self

        def inner_text(self) -> str:
            return self.body

        def goto(self, url: str, *, timeout: int) -> Response:
            assert timeout == 30_000
            self.navigation_calls += 1
            self.url = url
            response = Response()
            response.url = url
            return response

    class NavigationSession(Session):
        def __init__(self) -> None:
            super().__init__()
            self.page = Page()

    session = NavigationSession()
    configured = SiteConfig(
        "navigation-site",
        "SYNTHETIC",
        "https://example.invalid/login",
        None,
        "synthetic-user",
        "synthetic-password",
        start_time=time(9),
        end_time=time(10),
        weekdays=("MONDAY",),
        interval_seconds=10,
        timeout_seconds=7,
        log_file=tmp_path / "navigation-site.log",
        navigation=NavigationPlan(
            "1.0",
            (
                NavigationStep(
                    1,
                    "GET",
                    "https://example.invalid/target",
                    expected=ExpectedResult(text_marker="Synthetic monitoring target"),
                ),
            ),
            "https://example.invalid",
        ),
    )
    monkeypatch.setattr("adams_tutoria.monitoring.adapter_for_site", lambda _: Adapter(session))
    monitor = MultiSiteMonitor([configured], browser_factory=lambda: object())
    at_start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)

    login_events = monitor.tick(at_start, monotonic=0)
    reload_events = monitor.tick(at_start, monotonic=10)

    assert [event.kind for event in login_events] == [MonitorEventKind.LOGIN]
    assert [event.kind for event in reload_events] == [MonitorEventKind.RELOAD]
    assert session.page.navigation_calls == 2
    records = [json.loads(line) for line in configured.log_file.read_text().splitlines()]
    assert [(record["action"], record["result"]) for record in records] == [
        ("startup", "success"),
        ("navigation", "success"),
        ("login", "success"),
        ("navigation", "success"),
        ("reload", "success"),
    ]


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
        assert [record["action"] for record in records] == ["startup", "login", "reload"]
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
    assert '"category":"logging"' in text or '"category":"authentication"' in text
    for value in sensitive_values:
        assert value not in text
    assert configured.password not in text
    assert configured.username not in text


def test_failure_categories_are_safe_and_phase_specific(tmp_path) -> None:
    configured = SiteConfig(
        "categories",
        "SYNTHETIC",
        "https://example.invalid/login",
        "https://example.invalid/target",
        "synthetic-user",
        "synthetic-password",
        log_file=tmp_path / "categories.log",
    )
    from adams_tutoria.site_logging import SiteLogWriter

    writer = SiteLogWriter(configured)
    cases = (
        ("startup", "config", "Startup no disponible."),
        ("login", "authentication", "Login no confirmado."),
        ("navigation", "navigation", "Navegación no confirmada."),
        ("navigation", "timeout", "Operación agotó el tiempo."),
        ("navigation", "blocked", "Intervención humana requerida."),
        ("reload", "logging", "Registro local no disponible."),
    )
    for action, category, message in cases:
        assert writer.write(action=action, result="error", category=category, message=message)

    records = [json.loads(line) for line in configured.log_file.read_text().splitlines()]
    assert [
        (record["action"], record["category"], record["message"]) for record in records
    ] == list(cases)
    assert all(
        set(record)
        == {"timestamp", "site_id", "provider", "action", "result", "category", "message"}
        for record in records
    )


def test_human_intervention_diagnostic_is_mapped_to_controlled_blocked_category() -> None:
    from adams_tutoria.monitoring import _safe_diagnostic

    assert _safe_diagnostic("human_intervention_required", "navigation", "error") == (
        "blocked",
        "Intervención humana requerida.",
    )


def test_configured_log_path_and_early_failure_diagnostic_are_safe(tmp_path, monkeypatch) -> None:
    configured_path = tmp_path / "configured" / "monitor.log"
    configured = SiteConfig(
        "early-failure",
        "SYNTHETIC",
        "https://example.invalid/login",
        "https://example.invalid/target",
        "synthetic-user",
        "synthetic-secret",
        start_time=time(9),
        end_time=time(10),
        weekdays=("MONDAY",),
        log_file=configured_path,
    )

    class FailingAdapter:
        def login_session(self, request: object, *, browser_api: object) -> tuple[object, None]:
            del request, browser_api
            raise RuntimeError("synthetic failure with secret synthetic-secret")

    monkeypatch.setattr("adams_tutoria.monitoring.adapter_for_site", lambda _: FailingAdapter())
    monitor = MultiSiteMonitor([configured], browser_factory=lambda: object())

    events = monitor.tick(datetime(2026, 1, 5, 9, 0, tzinfo=UTC), monotonic=0)

    assert configured_path.exists()
    records = [json.loads(line) for line in configured_path.read_text().splitlines()]
    assert [record["action"] for record in records] == ["startup", "login"]
    assert records[-1]["result"] == "error"
    assert records[-1]["category"] == "authentication"
    assert records[-1]["message"] == "Login no confirmado."
    assert "synthetic-secret" not in configured_path.read_text()
    login_failure = next(event for event in events if event.kind is MonitorEventKind.ERROR)
    assert login_failure.phase == "login"
    assert login_failure.category == "authentication"


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


def test_reload_log_failure_keeps_runtime_and_emits_safe_logging_diagnostic(
    monkeypatch,
) -> None:
    session = Session()

    class ReloadLogFailure:
        calls = 0

        def write(
            self,
            *,
            action: str,
            result: str,
            category: str | None = None,
            message: str | None = None,
        ) -> bool:
            self.calls += 1
            if self.calls == 1:
                assert action == "startup"
                assert result == "success"
                assert category is None and message is None
                return True
            if self.calls == 2:
                assert action == "login"
                assert result == "success"
                assert category is None and message is None
                return True
            assert action == "reload"
            assert result == "success"
            assert category is None and message is None
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
    assert not session.closed
    assert monitor.tick(at_start, monotonic=20)[0].kind is MonitorEventKind.RELOAD
