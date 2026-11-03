"""Provider-neutral, one-shot login adapters.

Adapters deliberately return only an observable status and a safe message.  They
do not retain browser objects, credentials, cookies, or tokens.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from adams_tutoria.adams_login import AdamsLoginSettings, LoginResult, perform_login
from adams_tutoria.config import SiteConfig


class LoginStatus(StrEnum):
    """The only statuses exposed by a provider adapter."""

    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    """Immutable, secret-free result of one login attempt."""

    status: LoginStatus
    message: str


@dataclass(frozen=True, slots=True)
class LoginRequest:
    """In-memory login input; it must never be persisted or logged."""

    username: str
    password: str
    login_url: str
    target_url: str = ""


class LoginAdapter(Protocol):
    """Common contract independent of a provider's HTML or selectors."""

    def login(self, request: LoginRequest, *, browser_api: Any | None = None) -> LoginOutcome: ...


class UnknownProviderError(ValueError):
    """Raised when configuration names no registered provider."""


class AdamsLoginAdapter:
    """ADAMS adapter delegating selectors and resource handling to adams_login."""

    def login(self, request: LoginRequest, *, browser_api: Any | None = None) -> LoginOutcome:
        settings = AdamsLoginSettings(
            request.username, request.password, request.login_url, request.target_url
        )
        try:
            result = (
                perform_login(settings, browser_api=browser_api)
                if browser_api is not None
                else _playwright_login(settings)
            )
        except Exception:
            return LoginOutcome(LoginStatus.FAILED, "No se pudo completar el login.")
        return _outcome(result)


class UnimplementedLoginAdapter:
    """Reserved provider entry point; no login flow is attempted."""

    def login(self, request: LoginRequest, *, browser_api: Any | None = None) -> LoginOutcome:
        del request, browser_api
        return LoginOutcome(LoginStatus.FAILED, "El proveedor de login aún no está implementado.")


def _playwright_login(settings: AdamsLoginSettings) -> LoginResult:
    from adams_tutoria.adams_login import login_with_playwright

    return login_with_playwright(settings)


def _outcome(result: LoginResult) -> LoginOutcome:
    try:
        status = LoginStatus(result.status)
    except ValueError:
        return LoginOutcome(LoginStatus.FAILED, "El login produjo un estado no válido.")
    if status is LoginStatus.SUCCESS:
        message = "Login completado correctamente."
    elif status is LoginStatus.BLOCKED:
        message = "El login requiere intervención; se detiene sin intentar evitarla."
    else:
        message = "El login no pudo confirmarse."
    return LoginOutcome(status, message)


def request_from_site(site: SiteConfig) -> LoginRequest:
    """Build an ephemeral adapter request from validated site configuration."""

    return LoginRequest(site.username, site.password, site.login_url, site.target_url)


_FACTORIES: Mapping[str, Callable[[], LoginAdapter]] = {
    "ADAMS": AdamsLoginAdapter,
    "BETA": UnimplementedLoginAdapter,
}


def adapter_for_provider(provider: str) -> LoginAdapter:
    """Resolve a configured provider without starting any login attempt."""

    key = provider.strip().upper()
    try:
        return _FACTORIES[key]()
    except KeyError as exc:
        raise UnknownProviderError("Proveedor de login desconocido.") from exc


def adapter_for_site(site: SiteConfig) -> LoginAdapter:
    """Resolve the adapter selected by one validated ``SiteConfig``."""

    return adapter_for_provider(site.provider)
