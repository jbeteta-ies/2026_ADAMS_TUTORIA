"""Single-threaded, provider-neutral monitoring of independent sites."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from time import sleep
from typing import Any
from uuid import UUID, uuid4

from adams_tutoria.config import SiteConfig
from adams_tutoria.declarative_navigation import NavigationExecutor, NavigationStatus
from adams_tutoria.login_adapters import LoginAdapter, adapter_for_site, request_from_site
from adams_tutoria.scheduler import ScheduleEventKind, SiteScheduler, WindowPhase
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
    run_id: str | None = None


@dataclass
class _Runtime:
    site: SiteConfig
    adapter: LoginAdapter | None
    setup_error: str | None = None
    session: Any | None = None
    next_reload: float = 0.0
    active: bool = False
    last_monotonic: float | None = None


MAX_RETRY_BACKOFF_SECONDS = 30.0
_TERMINAL_NAVIGATION_CODES = frozenset(
    {"expected_result_not_confirmed", "no_response", "csrf_field_missing"}
)


class MultiSiteMonitor:
    """Coordinate scheduling, ephemeral login sessions, and safe reloads."""

    def __init__(
        self,
        sites: Iterable[SiteConfig],
        *,
        browser_factory: Callable[[], Any],
        log_writer_factory: Callable[[SiteConfig], SiteLogWriter] = SiteLogWriter,
        retry_backoff: Callable[[int], float] | None = None,
        retry_wait: Callable[[float], None] = sleep,
        run_id: str | None = None,
    ) -> None:
        configured_sites = tuple(sites)
        self._scheduler = SiteScheduler(configured_sites)
        candidate_run_id = run_id or str(uuid4())
        try:
            parsed_run_id = UUID(candidate_run_id)
            if parsed_run_id.version != 4:
                raise ValueError("run identifier must be UUID4")
        except (AttributeError, ValueError):
            parsed_run_id = uuid4()
        self.run_id = str(parsed_run_id)
        self._runtimes: dict[str, _Runtime] = {}
        self._loggers: dict[str, SiteLogWriter | None] = {}
        self._logger_failures: set[str] = set()
        self._logger_diagnostics: set[str] = set()
        for site in configured_sites:
            try:
                if log_writer_factory is SiteLogWriter:
                    self._loggers[site.id] = SiteLogWriter(site, run_id=self.run_id)
                else:
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
        self._retry_backoff = retry_backoff or _default_retry_backoff
        self._retry_wait = retry_wait

    @property
    def run_identifier(self) -> str:
        """Return the opaque identifier shared by this worker's diagnostics."""
        return self.run_id

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
                self._logging_diagnostic(
                    runtime,
                    now,
                    action="exit",
                    result="success",
                    error=None,
                )
                events.append(self._event(runtime.site.id, MonitorEventKind.EXIT, now))
            elif schedule_event.kind is ScheduleEventKind.INVALID:
                events.append(
                    self._event(
                        runtime.site.id,
                        MonitorEventKind.ERROR,
                        now,
                        "Configuración de ventana no válida.",
                    )
                )
        for runtime in self._runtimes.values():
            if runtime.active and runtime.session is not None:
                self._observe_clock(runtime, monotonic)
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
                    self._event(
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
                        terminal_diagnostic = diagnostics[-1] if diagnostics else None
                        if terminal_diagnostic is not None and _is_terminal_navigation_failure(
                            terminal_diagnostic
                        ):
                            with suppress(Exception):
                                session.close()
                            return [
                                *events,
                                *self._logged_events(
                                    runtime,
                                    now,
                                    self._event(
                                        runtime.site.id,
                                        MonitorEventKind.ERROR,
                                        now,
                                        "Navegación no confirmada; sitio aislado.",
                                        "navigation",
                                        "validation",
                                    ),
                                    action="navigation",
                                    result="error",
                                    error=terminal_diagnostic.code,
                                    response_metadata=terminal_diagnostic.response_metadata,
                                ),
                            ]
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
                                    self._event(
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
                    runtime.last_monotonic = monotonic
                    return [
                        *events,
                        *self._logged_events(
                            runtime,
                            now,
                            self._event(runtime.site.id, MonitorEventKind.LOGIN, now),
                            action="login",
                            result="success",
                        ),
                    ]
                if outcome.status.value in {
                    "blocked",
                    "human_intervention_required",
                    "captcha",
                    "mfa",
                    "session_expired",
                }:
                    break
            except Exception:
                pass
            if attempt == runtime.site.max_retries:
                break
            self._logging_diagnostic(
                runtime,
                now,
                action="retry",
                result="error",
                error="login_retry",
            )
            self._retry_wait(self._safe_retry_backoff(attempt))
        runtime.active = False
        return [
            *events,
            *self._logged_events(
                runtime,
                now,
                self._event(
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
            # Check immediately before every request, including retries.
            if not self._scheduler.is_active(runtime.site.id, now):
                self._close(runtime)
                runtime.active = False
                return [
                    *self._logged_events(
                        runtime,
                        now,
                        self._event(runtime.site.id, MonitorEventKind.EXIT, now),
                        action="exit",
                        result="success",
                    )
                ]
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
                        terminal_diagnostic = diagnostics[-1] if diagnostics else None
                        if terminal_diagnostic is not None and _is_terminal_navigation_failure(
                            terminal_diagnostic
                        ):
                            self._close(runtime)
                            runtime.active = False
                            return [
                                *navigation_events,
                                *self._logged_events(
                                    runtime,
                                    now,
                                    self._event(
                                        runtime.site.id,
                                        MonitorEventKind.ERROR,
                                        now,
                                        "Recarga no confirmada; sitio aislado.",
                                        "reload",
                                        "validation",
                                    ),
                                    action="reload",
                                    result="error",
                                    error=terminal_diagnostic.code,
                                    response_metadata=terminal_diagnostic.response_metadata,
                                ),
                            ]
                        terminal = (
                            diagnostics[-1].status if diagnostics else NavigationStatus.FAILED
                        )
                        if terminal in {
                            NavigationStatus.BLOCKED,
                            NavigationStatus.SESSION_EXPIRED,
                            NavigationStatus.CANCELLED,
                        }:
                            self._close(runtime)
                            runtime.active = False
                            category = (
                                "blocked"
                                if terminal is NavigationStatus.BLOCKED
                                else "authentication"
                                if terminal is NavigationStatus.SESSION_EXPIRED
                                else "navigation"
                            )
                            return [
                                *navigation_events,
                                *self._logged_events(
                                    runtime,
                                    now,
                                    self._event(
                                        runtime.site.id,
                                        MonitorEventKind.ERROR,
                                        now,
                                        "Recarga no completada; sitio aislado.",
                                        "reload",
                                        category,
                                    ),
                                    action="reload",
                                    result="error",
                                    error=(
                                        "human_intervention_required"
                                        if terminal is NavigationStatus.BLOCKED
                                        else "session_expired"
                                    ),
                                ),
                            ]
                        raise RuntimeError("navigation failed")
                else:
                    navigation_events = []
                    assert runtime.site.target_url is not None
                    runtime.session.reload(
                        runtime.site.target_url, timeout_seconds=runtime.site.timeout_seconds
                    )
                runtime.next_reload = monotonic + runtime.site.interval_seconds
                runtime.last_monotonic = monotonic
                return [
                    *navigation_events,
                    *self._logged_events(
                        runtime,
                        now,
                        self._event(runtime.site.id, MonitorEventKind.RELOAD, now),
                        action="reload",
                        result="success",
                    ),
                ]
            except Exception:
                if attempt == runtime.site.max_retries:
                    self._close(runtime)
                    runtime.active = False
                    event = self._event(
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
                self._logging_diagnostic(
                    runtime,
                    now,
                    action="retry",
                    result="error",
                    error="reload_retry",
                )
                self._retry_wait(self._safe_retry_backoff(attempt))
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
                self._event(
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
            self._event(
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

    def _event(
        self,
        site_id: str,
        kind: MonitorEventKind,
        at: datetime,
        message: str = "",
        phase: str | None = None,
        category: str | None = None,
    ) -> MonitorEvent:
        return MonitorEvent(site_id, kind, at, message, phase, category, self.run_id)

    def _safe_retry_backoff(self, attempt: int) -> float:
        """Return a finite, non-negative delay even for an injected policy."""
        try:
            value = self._retry_backoff(attempt)
            delay = float(value)
        except (ArithmeticError, TypeError, ValueError, OverflowError):
            return 0.0
        if not isfinite(delay):
            return 0.0
        return min(MAX_RETRY_BACKOFF_SECONDS, max(0.0, delay))

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

    def run_window(
        self,
        site_id: str,
        *,
        clock: Callable[[], datetime],
        monotonic: Callable[[], float],
        wait: Callable[[float], None] = sleep,
        should_stop: Callable[[], bool] | None = None,
        on_events: Callable[[tuple[MonitorEvent, ...]], None] | None = None,
    ) -> None:
        """Run the selected site once, without entering a second window."""
        stop = should_stop or (lambda: False)
        started = False
        while not stop():
            now = clock()
            phase = self._scheduler.phase(site_id, now)
            if phase is WindowPhase.AFTER and not started:
                return
            events = self.tick(now, monotonic=monotonic())
            if any(e.site_id == site_id and e.kind is MonitorEventKind.LOGIN for e in events):
                started = True
            if events and on_events is not None:
                on_events(events)
            if started and phase is WindowPhase.AFTER:
                return
            wait(1.0)

    def close(self) -> None:
        for runtime in self._runtimes.values():
            self._close(runtime)

    @staticmethod
    def _observe_clock(runtime: _Runtime, monotonic: float) -> None:
        previous = runtime.last_monotonic
        if previous is not None and (monotonic < previous or monotonic - previous > 7200):
            runtime.next_reload = monotonic
        runtime.last_monotonic = monotonic


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
        if error == "session_expired":
            return "authentication", "Login no confirmado."
        return "navigation", "Navegación no confirmada."
    if action == "retry":
        return "navigation", "Reintento por error recuperable."
    if action == "exit":
        return "config", "Ventana finalizada; sesión cerrada."
    if action == "reload":
        if error == "timeout":
            return "timeout", "Operación agotó el tiempo."
        if error == "scheduled_exit":
            return "config", "Ventana finalizada; sesión cerrada."
        return "navigation", "Navegación no confirmada."
    return "logging", "Registro local no disponible."


def _default_retry_backoff(attempt: int) -> float:
    return min(MAX_RETRY_BACKOFF_SECONDS, float(2**attempt))


def _is_terminal_navigation_failure(diagnostic: Any) -> bool:
    """Validation failures are terminal, not evidence of an expired session."""
    if diagnostic.code in _TERMINAL_NAVIGATION_CODES:
        return True
    metadata = diagnostic.response_metadata
    return bool(
        metadata is not None and metadata.get("expected_result_match") in {"no", "not_checkable"}
    )
