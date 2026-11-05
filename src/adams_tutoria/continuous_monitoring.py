"""Local command for running the multi-site monitor continuously."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

from adams_tutoria.config import SiteConfigError, load_sites_config
from adams_tutoria.monitoring import MultiSiteMonitor

CONFIG_ERROR = 2
RUNTIME_ERROR = 1
SUCCESS = 0


def _playwright_runner() -> tuple[Any, Callable[[], None]]:
    """Start Playwright lazily and return its provider API and safe closer."""
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()

    def close() -> None:
        playwright.stop()

    return playwright, close


def run_continuous(
    config_path: Path,
    *,
    browser_factory: Callable[[], Any] | None = None,
    resource_close: Callable[[], None] | None = None,
    stop_event: Event | None = None,
    monitor_factory: Callable[..., Any] = MultiSiteMonitor,
    site_id: str | None = None,
    once_window: bool = False,
    run_id: str | None = None,
) -> int:
    """Validate config and run until a cooperative stop is requested.

    Dependencies are injectable so tests never open a browser or wait forever.
    """
    if once_window and site_id is None:
        return CONFIG_ERROR
    try:
        configuration = load_sites_config(config_path)
    except KeyboardInterrupt:
        return SUCCESS
    except (OSError, SiteConfigError):
        return CONFIG_ERROR

    if site_id is not None:
        selected = next((site for site in configuration.sites if site.id == site_id), None)
        if selected is None:
            return CONFIG_ERROR
        configuration = replace(configuration, sites=(selected,))
    monitor: MultiSiteMonitor | None = None
    worker_run_id = run_id or str(uuid4())
    close_resources = resource_close
    try:
        if browser_factory is None:
            browser_api, close_resources = _playwright_runner()

            def browser_factory() -> Any:
                return browser_api

        try:
            monitor = monitor_factory(
                configuration.sites, browser_factory=browser_factory, run_id=worker_run_id
            )
        except TypeError as error:
            if "run_id" not in str(error):
                raise
            monitor = monitor_factory(configuration.sites, browser_factory=browser_factory)
        requested_stop = stop_event or Event()
        if once_window and site_id is not None:
            monitor.run_window(
                site_id,
                clock=lambda: datetime.now(UTC),
                monotonic=time.monotonic,
                should_stop=requested_stop.is_set,
            )
        else:
            monitor.run_forever(
                clock=lambda: datetime.now(UTC),
                monotonic=time.monotonic,
                should_stop=requested_stop.is_set,
            )
    except KeyboardInterrupt:
        return SUCCESS
    except Exception:
        return RUNTIME_ERROR
    finally:
        if monitor is not None:
            with suppress(Exception):
                monitor.close()
        if close_resources is not None:
            with suppress(Exception):
                close_resources()
    return SUCCESS


def _install_signal_handlers(stop_event: Event) -> dict[int, Any]:
    previous: dict[int, Any] = {}

    def request_stop(signum: int, _frame: Any) -> None:
        del signum
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, request_stop)
    return previous


def _restore_signal_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local continuous monitor command."""
    parser = argparse.ArgumentParser(description="Ejecuta la monitorización multi-sitio continua.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--site", dest="site_id")
    parser.add_argument("--once-window", action="store_true")
    args = parser.parse_args(argv)
    stop_event = Event()
    try:
        previous = _install_signal_handlers(stop_event)
    except (ValueError, OSError):
        print("No se pudieron instalar las señales de apagado.", file=sys.stderr)
        return RUNTIME_ERROR
    try:
        return run_continuous(
            args.config,
            stop_event=stop_event,
            site_id=args.site_id,
            once_window=args.once_window,
        )
    finally:
        _restore_signal_handlers(previous)


__all__ = ["CONFIG_ERROR", "RUNTIME_ERROR", "SUCCESS", "main", "run_continuous"]
