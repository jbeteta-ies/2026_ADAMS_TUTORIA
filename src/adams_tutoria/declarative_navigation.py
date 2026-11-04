"""Safe, declarative navigation over an existing ephemeral Playwright session.

This module deliberately exposes navigation only.  It does not click controls,
execute JavaScript, scrape pages, save responses, or perform arbitrary browser
automation.  A session is supplied by the already authenticated login flow and
is never owned or persisted by the navigation plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event
from time import monotonic
from typing import Any
from urllib.parse import urlparse, urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from adams_tutoria.response_metadata import (
    ExpectedResultMatch,
    ResponseMetadata,
    ResponseMetadataDict,
    ResponsePhase,
    ResponseResult,
)

MAX_STEPS = 20
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 120
_BLOCKED_MARKERS = ("captcha", "recaptcha", "mfa", "two-factor", "autenticación multifactor")
_LOGIN_MARKERS = ("iniciar sesión", "login", "nombre de usuario", "contraseña")


class NavigationError(ValueError):
    """Invalid or unsafe declarative navigation configuration."""


class NavigationStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    SESSION_EXPIRED = "session_expired"


class NavigationState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ExpectedResult:
    """A stable, non-sensitive signal used to verify one navigation step."""

    status_code: int | None = None
    url_path: str | None = None
    text_marker: str | None = None


@dataclass(frozen=True, slots=True)
class NavigationStep:
    """One read/navigation operation; no click, fill, or script actions exist."""

    order: int
    method: str
    url: str
    params: Mapping[str, str] = field(default_factory=dict)
    form_data: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    expected: ExpectedResult = ExpectedResult()
    csrf_field: str | None = None
    read_only: bool = False


@dataclass(frozen=True, slots=True)
class NavigationPlan:
    """Versioned plan independent from runtime credentials and browser state."""

    version: str
    steps: tuple[NavigationStep, ...]
    allowed_origin: str


@dataclass(frozen=True, slots=True)
class NavigationDiagnostic:
    status: NavigationStatus
    code: str
    step_order: int | None = None
    response_metadata: ResponseMetadataDict | None = None


class NavigationPlanValidator:
    """Validate plans before any browser operation is started."""

    def validate(self, plan: NavigationPlan) -> None:
        if not plan.version.strip():
            raise NavigationError("La versión del contrato es obligatoria.")
        origin = _origin(plan.allowed_origin)
        if not plan.steps or len(plan.steps) > MAX_STEPS:
            raise NavigationError("El plan debe contener entre 1 y 20 pasos.")
        orders = [step.order for step in plan.steps]
        if any(
            isinstance(order, bool) or not isinstance(order, int) for order in orders
        ) or orders != list(range(1, len(orders) + 1)):
            raise NavigationError("El orden de los pasos debe ser consecutivo.")
        for step in plan.steps:
            if step.method not in {"GET", "POST"}:
                raise NavigationError("Solo se permiten métodos GET y POST.")
            if _origin(step.url) != origin:
                raise NavigationError("Cada paso debe permanecer en el origen permitido.")
            if (
                isinstance(step.timeout_seconds, bool)
                or not isinstance(step.timeout_seconds, int)
                or step.timeout_seconds not in range(MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS + 1)
            ):
                raise NavigationError("El timeout debe estar entre 1 y 120 segundos.")
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in step.params.items()):
                raise NavigationError("Los parámetros deben ser texto.")
            if not all(
                isinstance(k, str) and isinstance(v, str) for k, v in step.form_data.items()
            ):
                raise NavigationError("Los datos de formulario deben ser texto.")
            if step.csrf_field is not None and not step.csrf_field.strip():
                raise NavigationError("El campo CSRF no puede estar vacío.")
            if not _has_expected_signal(step.expected):
                raise NavigationError(
                    "Cada paso debe declarar al menos una señal de resultado esperado."
                )
            if step.expected.status_code is not None and (
                isinstance(step.expected.status_code, bool)
                or not isinstance(step.expected.status_code, int)
                or not 100 <= step.expected.status_code <= 599
            ):
                raise NavigationError("El código esperado debe ser HTTP 2xx o 3xx.")
            if step.expected.url_path is not None and not step.expected.url_path.startswith("/"):
                raise NavigationError("La ruta esperada debe ser absoluta.")
        for step in plan.steps:
            if step.method == "POST":
                if not step.read_only:
                    raise NavigationError("Un POST declarativo requiere read_only: true explícito.")
                if not step.form_data:
                    raise NavigationError("Un POST declarativo requiere form_data explícito.")
                if step.params:
                    raise NavigationError("Los parámetros de query solo se permiten en GET.")
            elif step.form_data:
                raise NavigationError("Los datos de formulario solo se permiten en POST.")


class NavigationExecutor:
    """Execute a validated plan against an injected, already authenticated page."""

    def __init__(self, session: Any, *, cancel_event: Event | None = None) -> None:
        self._session = session
        self._cancel_event = cancel_event or Event()
        self.state = NavigationState.CREATED

    def execute(self, plan: NavigationPlan) -> tuple[NavigationDiagnostic, ...]:
        NavigationPlanValidator().validate(plan)
        self.state = NavigationState.RUNNING
        diagnostics: list[NavigationDiagnostic] = []
        for step in plan.steps:
            if self._cancel_event.is_set():
                self.state = NavigationState.CANCELLED
                diagnostics.append(NavigationDiagnostic(NavigationStatus.CANCELLED, "cancelled"))
                break
            diagnostic = self._run_step(step, plan.allowed_origin)
            diagnostics.append(diagnostic)
            if diagnostic.status is not NavigationStatus.SUCCESS:
                self.state = _state_for(diagnostic.status)
                break
        else:
            self.state = NavigationState.SUCCEEDED
        return tuple(diagnostics)

    def _run_step(self, step: NavigationStep, allowed_origin: str) -> NavigationDiagnostic:
        started = monotonic()
        status: int | None = None
        redirected = False
        match = ExpectedResultMatch.NOT_CHECKABLE
        result = ResponseResult.FAILED
        code = "navigation_error"
        try:
            url = _with_params(step.url, step.params)
            data = dict(step.form_data)
            if step.csrf_field:
                locator = self._session.page.locator(f"input[name='{step.csrf_field}']").first
                if locator.count() == 0:
                    return self._diagnostic(
                        step,
                        "csrf_field_missing",
                        status,
                        redirected,
                        match,
                        result,
                        started,
                    )
                data[step.csrf_field] = locator.input_value()
            if step.method == "GET":
                # page.goto is browser navigation.  It deliberately receives no
                # HTTP method/body arguments: Playwright only supports GET here.
                response = self._session.page.goto(url, timeout=step.timeout_seconds * 1000)
                observed_url = getattr(response, "url", None) or self._session.page.url
                observed_page = self._session.page
                response_text = None
            else:
                # APIRequestContext belongs to the authenticated browser context,
                # so its cookie jar is shared without copying or persisting it.
                response = self._session.request_context.post(
                    step.url,
                    form=data,
                    timeout=step.timeout_seconds * 1000,
                )
                observed_url = getattr(response, "url", None) or step.url
                observed_page = None
                response_text = _response_text(response)
            if response is None:
                code = "no_response"
                return self._diagnostic(step, code, status, redirected, match, result, started)
            redirected = _effective_url(observed_url) != _effective_url(url)
            if _origin(observed_url) != _origin(allowed_origin):
                code = "external_redirect"
                return self._diagnostic(step, code, status, redirected, match, result, started)
            status_value = getattr(response, "status", None)
            status = (
                status_value
                if isinstance(status_value, int)
                and not isinstance(status_value, bool)
                and 100 <= status_value <= 599
                else None
            )
            if _blocked(observed_page, response_text):
                code, result = "human_intervention_required", ResponseResult.BLOCKED
                return self._diagnostic(
                    step, code, status, redirected, match, result, started, NavigationStatus.BLOCKED
                )
            if _looks_like_login(observed_page, response_text):
                code = "session_expired"
                return self._diagnostic(
                    step,
                    code,
                    status,
                    redirected,
                    match,
                    result,
                    started,
                    NavigationStatus.SESSION_EXPIRED,
                )
            match = (
                ExpectedResultMatch.YES
                if _matches(step.expected, observed_page, observed_url, response_text, status)
                else ExpectedResultMatch.NO
            )
            if match is ExpectedResultMatch.NO:
                code = "expected_result_not_confirmed"
                return self._diagnostic(step, code, status, redirected, match, result, started)
            code, result = "step_succeeded", ResponseResult.OK
            return self._diagnostic(
                step, code, status, redirected, match, result, started, NavigationStatus.SUCCESS
            )
        except (TimeoutError, PlaywrightTimeoutError):
            code, result = "timeout", ResponseResult.TIMEOUT
            return self._diagnostic(step, code, status, redirected, match, result, started)
        except Exception:
            return self._diagnostic(step, code, status, redirected, match, result, started)

    def _diagnostic(
        self,
        step: NavigationStep,
        code: str,
        status: int | None,
        redirected: bool,
        match: ExpectedResultMatch,
        result: ResponseResult,
        started: float,
        status_value: NavigationStatus = NavigationStatus.FAILED,
    ) -> NavigationDiagnostic:
        metadata = ResponseMetadata(
            step=_safe_step_id(step),
            phase=ResponsePhase.NAVIGATION,
            method=step.method,
            status_code=status,
            expected_result_match=match,
            redirected=redirected,
            duration=min(24 * 60 * 60, max(0.0, monotonic() - started)),
            result=result,
        ).as_dict()
        return NavigationDiagnostic(status_value, code, step.order, metadata)


def _safe_step_id(step: NavigationStep) -> str:
    """Use only the validated ordinal; URLs are neither stored nor hashed."""
    return f"step-{step.order}"


def _effective_url(url: str) -> tuple[str, str, str, str]:
    """Return the in-memory URL parts relevant to redirect detection."""
    parsed = urlsplit(url)
    return parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise NavigationError("Las URLs deben ser HTTP(S), sin credenciales embebidas.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _with_params(url: str, params: Mapping[str, str]) -> str:
    if not params:
        return url
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parsed = urlsplit(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(params.items())
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _response_text(response: Any) -> str:
    text = response.text()
    return text if isinstance(text, str) else ""


def _page_or_response_text(page: Any | None, response_text: str | None) -> str:
    if response_text is not None:
        return response_text.lower()
    if page is None:
        return ""
    return page.locator("body").inner_text().lower()


def _blocked(page: Any | None, response_text: str | None = None) -> bool:
    text = _page_or_response_text(page, response_text)
    return any(marker in text for marker in _BLOCKED_MARKERS)


def _looks_like_login(page: Any | None, response_text: str | None = None) -> bool:
    text = _page_or_response_text(page, response_text)
    return any(marker in text for marker in _LOGIN_MARKERS)


def _has_expected_signal(expected: ExpectedResult) -> bool:
    return any(
        signal is not None and (not isinstance(signal, str) or bool(signal.strip()))
        for signal in (expected.status_code, expected.url_path, expected.text_marker)
    )


def _matches(
    expected: ExpectedResult,
    page: Any | None,
    observed_url: str,
    response_text: str | None,
    status: int | None,
) -> bool:
    if expected.status_code is not None and status != expected.status_code:
        return False
    if expected.url_path is not None and urlparse(observed_url).path != expected.url_path:
        return False
    return not (
        expected.text_marker is not None
        and expected.text_marker.lower() not in _page_or_response_text(page, response_text)
    )


def _state_for(status: NavigationStatus) -> NavigationState:
    return {
        NavigationStatus.BLOCKED: NavigationState.BLOCKED,
        NavigationStatus.CANCELLED: NavigationState.CANCELLED,
    }.get(status, NavigationState.FAILED)


__all__ = [
    "ExpectedResult",
    "NavigationDiagnostic",
    "NavigationExecutor",
    "NavigationError",
    "NavigationPlan",
    "NavigationPlanValidator",
    "NavigationState",
    "NavigationStatus",
    "NavigationStep",
]
