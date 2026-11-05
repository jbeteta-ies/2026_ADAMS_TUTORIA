"""Synthetic tests for the continuous monitoring command."""

from datetime import UTC, datetime, time
from pathlib import Path
from threading import Event

import adams_tutoria.continuous_monitoring as continuous_monitoring
from adams_tutoria.config import SiteConfig
from adams_tutoria.continuous_monitoring import CONFIG_ERROR, RUNTIME_ERROR, SUCCESS, run_continuous
from adams_tutoria.monitoring import MultiSiteMonitor

VALID = """
schema_version: 1
sites:
  - id: synthetic-site
    provider: BETA
    login_url: https://example.invalid/login
    target_url: https://example.invalid/target
    username: synthetic-user
    password: synthetic-password
"""


class FakeMonitor:
    def __init__(self, sites, *, browser_factory):
        self.sites = tuple(sites)
        self.browser_factory = browser_factory
        self.closed = False

    def run_forever(self, *, clock, monotonic, should_stop):
        assert clock().tzinfo is not None
        assert monotonic() >= 0
        assert should_stop()

    def close(self):
        self.closed = True


def test_invalid_config_is_rejected_before_monitor_creation(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("schema_version: 2\nsites: []\n", encoding="utf-8")
    created = False

    def factory(*args, **kwargs):
        nonlocal created
        created = True
        return FakeMonitor(*args, **kwargs)

    assert run_continuous(path, monitor_factory=factory) == CONFIG_ERROR
    assert not created


def test_keyboard_interrupt_during_config_load_is_clean_shutdown(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(VALID, encoding="utf-8")
    created = False
    opened = False

    def factory(*args, **kwargs):
        nonlocal created
        created = True
        return FakeMonitor(*args, **kwargs)

    def browser_factory():
        nonlocal opened
        opened = True
        return object()

    def interrupted_load(_path):
        raise KeyboardInterrupt

    monkeypatch.setattr(continuous_monitoring, "load_sites_config", interrupted_load)

    assert (
        run_continuous(
            path,
            browser_factory=browser_factory,
            monitor_factory=factory,
        )
        == SUCCESS
    )
    assert not created
    assert not opened


def test_stop_closes_monitor_and_external_resources(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(VALID, encoding="utf-8")
    closed: list[str] = []
    stop = Event()
    stop.set()
    assert (
        run_continuous(
            path,
            browser_factory=lambda: object(),
            resource_close=lambda: closed.append("resource"),
            stop_event=stop,
            monitor_factory=FakeMonitor,
        )
        == SUCCESS
    )
    assert closed == ["resource"]


def test_runtime_failure_returns_safe_status_and_still_closes(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(VALID, encoding="utf-8")
    closed: list[str] = []

    class BrokenMonitor(FakeMonitor):
        def run_forever(self, **kwargs):
            del kwargs
            raise RuntimeError("synthetic private failure")

    assert (
        run_continuous(
            path,
            browser_factory=lambda: object(),
            resource_close=lambda: closed.append("resource"),
            monitor_factory=BrokenMonitor,
        )
        == RUNTIME_ERROR
    )
    assert closed == ["resource"]


def test_unknown_site_is_rejected_before_playwright(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(VALID, encoding="utf-8")
    opened = False

    def browser_factory():
        nonlocal opened
        opened = True
        return object()

    assert (
        run_continuous(
            path,
            site_id="missing",
            once_window=True,
            browser_factory=browser_factory,
        )
        == CONFIG_ERROR
    )
    assert not opened


def test_cli_once_window_requires_site_without_starting_monitor(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(VALID, encoding="utf-8")
    created = False

    def factory(*args, **kwargs):
        nonlocal created
        created = True
        return FakeMonitor(*args, **kwargs)

    monkeypatch.setattr(continuous_monitoring, "MultiSiteMonitor", factory)
    monkeypatch.setattr(continuous_monitoring, "_install_signal_handlers", lambda event: {})
    monkeypatch.setattr(continuous_monitoring, "_restore_signal_handlers", lambda previous: None)

    assert continuous_monitoring.main(["--config", str(path), "--once-window"]) == CONFIG_ERROR
    assert not created


def test_once_window_waits_on_non_enabled_day_without_opening_browser(monkeypatch) -> None:
    configured = SiteConfig(
        "synthetic-site",
        "BETA",
        "https://example.invalid/login",
        "https://example.invalid/target",
        "synthetic-user",
        "synthetic-password",
        start_time=time(9),
        end_time=time(10),
        weekdays=("MONDAY",),
    )
    opened = False
    waits: list[float] = []
    stop = Event()
    ticks = iter((datetime(2026, 1, 6, 9, 30, tzinfo=UTC),))

    def browser_factory():
        nonlocal opened
        opened = True
        return object()

    monitor = MultiSiteMonitor([configured], browser_factory=browser_factory)
    monitor.run_window(
        configured.id,
        clock=lambda: next(ticks),
        monotonic=lambda: 0.0,
        wait=lambda seconds: (waits.append(seconds), stop.set()),
        should_stop=stop.is_set,
    )

    assert not opened
    assert waits == [1.0]
