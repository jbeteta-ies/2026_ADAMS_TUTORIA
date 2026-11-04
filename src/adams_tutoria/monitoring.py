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
from adams_tutoria.declarative_navigation import NavigationExecutor, NavigationStatus
from adams_tutoria.login_adapters import LoginAdapter, adapter_for_site, request_from_site
from adams_tutoria.scheduler import ScheduleEventKind, SiteScheduler
from adams_tutoria.site_logging import SiteLogWriter


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
    phase: str | None = None
    category: str | None = None


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

    def __init__(
        self,
        sites: Iterable[SiteConfig],
        *,
        browser_factory: Callable[[], Any],
        log_writer_factory: Callable[[SiteConfig], SiteLogWriter] = SiteLogWriter,
    ) -> None:
        configured_sites = tuple(sites)
        self._scheduler = SiteScheduler(configured_sites)
        self._runtimes: dict[str, _Runtime] = {}
        self._loggers: dict[str, SiteLogWriter | None] = {}
        self._logger_failures: set[str] = set()
        self._logger_diagnostics: set[str] = set()
        for site in configured_sites:
            try:
                self._loggers[site.id] = log_writer_factory(site)
            except Exception:
                self._loggers[site.id] = None
                self._logger_failures.add(site.id)
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
                events.extend(self._reload(runtime, now, monotonic))
        return tuple(events)

    def _enter(self, runtime: _Runtime, now: datetime, monotonic: float) -> list[MonitorEvent]:
        events = self._logging_diagnostic(
            runtime, now, action="startup", result="success", error=None
        )
        if runtime.adapter is None:
            runtime.active = False
            return [
                *events,
                *self._logged_events(
                    runtime,
                    now,
                    MonitorEvent(
                        runtime.site.id,
                        MonitorEventKind.ERROR,
                        now,
                        "Sitio aislado.",
                        "startup",
                        "config",
                    ),
                    action="startup",
                    result="error",
                    error="config",
                ),
            ]
        # max_retries counts attempts after the first one.
        for attempt in range(runtime.site.max_retries + 1):
            try:
                outcome, session = runtime.adapter.login_session(
                    request_from_site(runtime.site), browser_api=self._browser_factory()
                )
                if outcome.status.value == "success" and session is not None:
                    if runtime.site.navigation is not None:
                        diagnostics = NavigationExecutor(session).execute(runtime.site.navigation)
                        for diagnostic in diagnostics:
                            events.extend(
                                self._logging_diagnostic(
                                    runtime,
                                    now,
                                    action="navigation",
                                    result=(
                                        "success"
                                        if diagnostic.status is NavigationStatus.SUCCESS
                                        else "error"
                                    ),
                                    error=diagnostic.code,
                                    response_metadata=diagnostic.response_metadata,
                                )
                            )
                        if (
                            not diagnostics
                            or diagnostics[-1].status is not NavigationStatus.SUCCESS
                        ):
                            with suppress(Exception):
                                session.close()
                            return [
                                *events,
                                *self._logged_events(
                                    runtime,
                                    now,
                                    MonitorEvent(
                                        runtime.site.id,
                                        MonitorEventKind.ERROR,
                                        now,
                                        "Navegación post-login no confirmada; sitio aislado.",
                                        "navigation",
                                        "navigation",
                                    ),
                                    action="navigation",
                                    result="error",
                                    error="navigation phase failed",
                                    response_metadata=None,
                                ),
                            ]
                    runtime.session = session
                    runtime.active = True
                    runtime.next_reload = monotonic + runtime.site.interval_seconds
                    return [
                        *events,
                        *self._logged_events(
                            runtime,
                            now,
                            MonitorEvent(runtime.site.id, MonitorEventKind.LOGIN, now),
                            action="login",
                            result="success",
                        ),
                    ]
                if outcome.status.value == "blocked":
                    break
            except Exception:
                pass
            if attempt == runtime.site.max_retries:
                break
        runtime.active = False
        return [
            *events,
            *self._logged_events(
                runtime,
                now,
                MonitorEvent(
                    runtime.site.id,
                    MonitorEventKind.ERROR,
                    now,
                    "Login no confirmado; sitio aislado.",
                    "login",
                    "authentication",
                ),
                action="login",
                result="error",
                error="login phase failed",
            ),
        ]

    def _reload(self, runtime: _Runtime, now: datetime, monotonic: float) -> list[MonitorEvent]:
        assert runtime.session is not None
        for attempt in range(runtime.site.max_retries + 1):
            try:
                navigation_metadata = None
                if runtime.site.navigation is not None:
                    diagnostics = NavigationExecutor(runtime.session).execute(
                        runtime.site.navigation
                    )
                    navigation_events = []
                    for diagnostic in diagnostics:
                        navigation_events.extend(
                            self._logging_diagnostic(
                                runtime,
                                now,
                                action="navigation",
                                result=(
                                    "success"
                                    if diagnostic.status is NavigationStatus.SUCCESS
                                    else "error"
                                ),
                                error=diagnostic.code,
                                response_metadata=diagnostic.response_metadata,
                            )
                        )
                    if not diagnostics or diagnostics[-1].status is not NavigationStatus.SUCCESS:
                        raise RuntimeError("navigation failed")
                else:
                    navigation_events = []
                    assert runtime.site.target_url is not None
                    runtime.session.reload(
                        runtime.site.target_url, timeout_seconds=runtime.site.timeout_seconds
                    )
                runtime.next_reload = monotonic + runtime.site.interval_seconds
                return [
                    *navigation_events,
                    *self._logged_events(
                        runtime,
                        now,
                        MonitorEvent(runtime.site.id, MonitorEventKind.RELOAD, now),
                        action="reload",
                        result="success",
                    ),
                ]
            except Exception:
                if attempt == runtime.site.max_retries:
                    self._close(runtime)
                    runtime.active = False
                    event = MonitorEvent(
                        runtime.site.id,
                        MonitorEventKind.ERROR,
                        now,
                        "Recarga no completada; sitio aislado.",
                        "reload",
                        "navigation",
                    )
                    return [
                        event,
                        *self._logging_diagnostic(
                            runtime,
                            now,
                            action="reload",
                            result="error",
                            error="reload phase failed",
                            response_metadata=navigation_metadata,
                        ),
                    ]
        raise AssertionError("unreachable")

    def _logged_events(
        self,
        runtime: _Runtime,
        now: datetime,
        event: MonitorEvent,
        *,
        action: str,
        result: str,
        error: str | None = None,
        response_metadata: object | None = None,
    ) -> list[MonitorEvent]:
        return [
            event,
            *self._logging_diagnostic(
                runtime,
                now,
                action=action,
                result=result,
                error=error,
                response_metadata=response_metadata,
            ),
        ]

    def _logged_event(
        self,
        runtime: _Runtime,
        now: datetime,
        event: MonitorEvent,
        *,
        action: str,
        result: str,
        error: str | None = None,
    ) -> MonitorEvent:
        self._logging_diagnostic(runtime, now, action=action, result=result, error=error)
        return event

    def _logging_diagnostic(
        self,
        runtime: _Runtime,
        now: datetime,
        *,
        action: str,
        result: str,
        error: str | None,
        response_metadata: object | None = None,
    ) -> list[MonitorEvent]:
        if runtime.site.id in self._logger_failures:
            if runtime.site.id in self._logger_diagnostics:
                return []
            self._logger_diagnostics.add(runtime.site.id)
            return [
                MonitorEvent(
                    runtime.site.id,
                    MonitorEventKind.ERROR,
                    now,
                    "Registro local no disponible.",
                    "logging",
                    "logging",
                )
            ]
        writer = self._loggers.get(runtime.site.id)
        if writer is not None:
            try:
                category, message = _safe_diagnostic(error, action, result)
                arguments: dict[str, object] = {
                    "action": action,
                    "result": result,
                    "category": category,
                    "message": message,
                }
                if response_metadata is not None:
                    arguments["response_metadata"] = response_metadata
                try:
                    written = writer.write(**arguments)  # type: ignore[arg-type]
                except TypeError:
                    # Preserve compatibility with injected legacy writers.
                    arguments.pop("response_metadata", None)
                    written = writer.write(**arguments)  # type: ignore[arg-type]
                if written:
                    return []
            except Exception:
                pass
        # A local log is diagnostic only.  Isolate a broken writer once so a
        # logging failure cannot stop or repeatedly retry the site runtime.
        self._loggers[runtime.site.id] = None
        self._logger_failures.add(runtime.site.id)
        self._logger_diagnostics.add(runtime.site.id)
        return [
            MonitorEvent(
                runtime.site.id,
                MonitorEventKind.ERROR,
                now,
                "Registro local no disponible.",
                "logging",
                "logging",
            )
        ]

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


def _safe_diagnostic(error: str | None, action: str, result: str) -> tuple[str | None, str | None]:
    if result == "success":
        return None, None
    if action == "startup":
        return "config", "Startup no disponible."
    if action == "login":
        return "authentication", "Login no confirmado."
    if action == "navigation":
        if error == "timeout":
            return "timeout", "Operación agotó el tiempo."
        if error in {"blocked", "human_intervention_required"}:
            return "blocked", "Intervención humana requerida."
        return "navigation", "Navegación no confirmada."
    if action == "reload":
        if error == "timeout":
            return "timeout", "Operación agotó el tiempo."
        return "navigation", "Navegación no confirmada."
    return "logging", "Registro local no disponible."
