"""Single-threaded, provider-neutral monitoring of independent sites."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from time import sleep
from typing import Any

from adams_tutoria.config import SiteConfig
from adams_tutoria.login_adapters import LoginAdapter, adapter_for_site, request_from_site
from adams_tutoria.scheduler import ScheduleEventKind, SiteScheduler


class MonitorEventKind(StrEnum):
    LOGIN = "login"
    RELOAD = "reload"
    EXIT = "exit"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class MonitorEvent:
    site_id: str
    kind: MonitorEventKind
    at: datetime
    message: str = ""


@dataclass
class _Runtime:
    site: SiteConfig
    adapter: LoginAdapter | None
    setup_error: str | None = None
    session: Any | None = None
    next_reload: float = 0.0
    active: bool = False


class MultiSiteMonitor:
    """Coordinate scheduling, ephemeral login sessions, and safe reloads."""

    def __init__(self, sites: Iterable[SiteConfig], *, browser_factory: Callable[[], Any]) -> None:
        configured_sites = tuple(sites)
        self._scheduler = SiteScheduler(configured_sites)
        self._runtimes: dict[str, _Runtime] = {}
        for site in configured_sites:
            try:
                adapter = adapter_for_site(site)
            except Exception:
                self._runtimes[site.id] = _Runtime(
                    site, None, "No se pudo preparar el proveedor del sitio."
                )
            else:
                self._runtimes[site.id] = _Runtime(site, adapter)
        self._browser_factory = browser_factory

    def tick(self, now: datetime, *, monotonic: float) -> tuple[MonitorEvent, ...]:
        events: list[MonitorEvent] = []
        for schedule_event in self._scheduler.tick(now):
            runtime = self._runtimes.get(schedule_event.site_id)
            if runtime is None:
                continue
            if schedule_event.kind is ScheduleEventKind.ENTER:
                events.extend(self._enter(runtime, now, monotonic))
            elif schedule_event.kind is ScheduleEventKind.EXIT:
                self._close(runtime)
                runtime.active = False
                events.append(MonitorEvent(runtime.site.id, MonitorEventKind.EXIT, now))
            elif schedule_event.kind is ScheduleEventKind.INVALID:
                events.append(
                    MonitorEvent(
                        runtime.site.id,
                        MonitorEventKind.ERROR,
                        now,
                        "Configuración de ventana no válida.",
                    )
                )
        for runtime in self._runtimes.values():
            if runtime.active and runtime.session is not None and monotonic >= runtime.next_reload:
                events.append(self._reload(runtime, now, monotonic))
        return tuple(events)

    def _enter(self, runtime: _Runtime, now: datetime, monotonic: float) -> list[MonitorEvent]:
        if runtime.adapter is None:
            runtime.active = False
            return [
                MonitorEvent(
                    runtime.site.id,
                    MonitorEventKind.ERROR,
                    now,
                    runtime.setup_error or "Sitio aislado.",
                )
            ]
        # max_retries counts attempts after the first one.
        for attempt in range(runtime.site.max_retries + 1):
            try:
                outcome, session = runtime.adapter.login_session(
                    request_from_site(runtime.site), browser_api=self._browser_factory()
                )
                if outcome.status.value == "success" and session is not None:
                    runtime.session = session
                    runtime.active = True
                    runtime.next_reload = monotonic + runtime.site.interval_seconds
                    return [MonitorEvent(runtime.site.id, MonitorEventKind.LOGIN, now)]
                if outcome.status.value == "blocked":
                    break
            except Exception:
                pass
            if attempt == runtime.site.max_retries:
                break
        runtime.active = False
        return [
            MonitorEvent(
                runtime.site.id, MonitorEventKind.ERROR, now, "Login no confirmado; sitio aislado."
            )
        ]

    def _reload(self, runtime: _Runtime, now: datetime, monotonic: float) -> MonitorEvent:
        assert runtime.session is not None
        for attempt in range(runtime.site.max_retries + 1):
            try:
                runtime.session.reload(
                    runtime.site.target_url, timeout_seconds=runtime.site.timeout_seconds
                )
                runtime.next_reload = monotonic + runtime.site.interval_seconds
                return MonitorEvent(runtime.site.id, MonitorEventKind.RELOAD, now)
            except Exception:
                if attempt == runtime.site.max_retries:
                    self._close(runtime)
                    runtime.active = False
                    return MonitorEvent(
                        runtime.site.id,
                        MonitorEventKind.ERROR,
                        now,
                        "Recarga no completada; sitio aislado.",
                    )
        raise AssertionError("unreachable")

    def _close(self, runtime: _Runtime) -> None:
        if runtime.session is not None:
            with suppress(Exception):
                runtime.session.close()
            runtime.session = None

    def run_forever(
        self,
        *,
        clock: Callable[[], datetime],
        monotonic: Callable[[], float],
        wait: Callable[[float], None] = sleep,
        should_stop: Callable[[], bool] | None = None,
        on_events: Callable[[tuple[MonitorEvent, ...]], None] | None = None,
    ) -> None:
        stop = should_stop or (lambda: False)
        while not stop():
            events = self.tick(clock(), monotonic=monotonic())
            if events and on_events is not None:
                on_events(events)
            wait(1.0)

    def close(self) -> None:
        for runtime in self._runtimes.values():
            self._close(runtime)


__all__ = ["MonitorEvent", "MonitorEventKind", "MultiSiteMonitor"]
