"""One-shot, non-persistent browser login prototype for ADAMS."""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class AdamsLoginSettings:
    """Login settings held in memory; no session or credential storage."""

    username: str
    password: str
    login_url: str
    target_url: str = ""
    interval_seconds: int = 300
    timeout_seconds: int = 30

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> AdamsLoginSettings:
        values = os.environ if environ is None else environ
        return cls(
            _required(values, "ADAMS_USERNAME"),
            _required(values, "ADAMS_PASSWORD"),
            _required(values, "ADAMS_LOGIN_URL"),
        )


@dataclass(frozen=True)
class LoginResult:
    status: str
    message: str


class LoginSession:
    """An in-memory browser session owned by one monitored site."""

    def __init__(self, browser: Any, context: Any, page: Any) -> None:
        self._browser = browser
        self._context = context
        self.page = page
        self._closed = False

    @property
    def request_context(self) -> Any:
        """The request API bound to this context's in-memory cookie jar."""
        if self._closed:
            raise RuntimeError("login session is closed")
        return self._context.request

    def reload(self, url: str, *, timeout_seconds: int) -> None:
        if self._closed:
            raise RuntimeError("login session is closed")
        _goto(self.page, url, timeout_seconds)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._context.close()
            self._browser.close()


def perform_login_session(
    settings: AdamsLoginSettings, *, browser_api: Any, logintoken_field: str | None = None
) -> tuple[LoginResult, LoginSession | None]:
    """Attempt login and return an ephemeral session for the caller to close."""
    _validate_url(settings.login_url)
    browser: Any | None = None
    context: Any | None = None
    try:
        browser = browser_api.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        session = LoginSession(browser, context, page)
        _goto(page, settings.login_url, settings.timeout_seconds)
        username = _first_visible(
            page,
            (
                "input[name='nombre']",
                "input[name='username']",
                "input[name*='user']",
                "input[type='email']",
            ),
        )
        password = _first_visible(
            page, ("input[name='clave']", "input[name='password']", "input[type='password']")
        )
        if logintoken_field is not None:
            logintoken = _first_value(page, logintoken_field)
            if logintoken is None:
                session.close()
                return (
                    LoginResult("failed", "No se pudo obtener el token dinámico de login."),
                    None,
                )
            # The token is already present in the form and is submitted with the
            # browser POST.  Reading it validates that this login attempt has a
            # runtime token without trying to fill a hidden Moodle input.
        submit = _first_visible(
            page,
            (
                "button[name='Submit']",
                "input[name='Submit']",
                "form button[type='submit']",
                "form input[type='submit']",
                "button[type='submit']",
                "input[type='submit']",
            ),
        )
        if username is None or password is None or submit is None:
            session.close()
            return LoginResult("failed", "No se detectó un formulario de login compatible."), None
        username.fill(settings.username)
        password.fill(settings.password)
        submit.click()
        if _is_blocked(page):
            session.close()
            return LoginResult(
                "blocked", "El login requiere CAPTCHA o MFA; se detiene sin intentar evitarlo."
            ), None
        if page.url != settings.login_url or _has_success_marker(page):
            return LoginResult("success", "Login completado correctamente."), session
        session.close()
        return LoginResult("failed", "El login no pudo confirmarse."), None
    except Exception:
        _close_resources(context, browser)
        raise


def perform_login(settings: AdamsLoginSettings, *, browser_api: Any) -> LoginResult:
    """Submit one login attempt using an injected Playwright-like API."""
    _validate_url(settings.login_url)
    browser: Any | None = None
    context: Any | None = None
    try:
        browser = browser_api.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        _goto(page, settings.login_url, settings.timeout_seconds)
        username = _first_visible(
            page,
            (
                "input[name='nombre']",
                "input[name='username']",
                "input[name*='user']",
                "input[type='email']",
            ),
        )
        password = _first_visible(
            page, ("input[name='clave']", "input[name='password']", "input[type='password']")
        )
        submit = _first_visible(
            page,
            (
                "button[name='Submit']",
                "input[name='Submit']",
                "form button[type='submit']",
                "form input[type='submit']",
                "button[type='submit']",
                "input[type='submit']",
            ),
        )
        if username is None or password is None or submit is None:
            return LoginResult("failed", "No se detectó un formulario de login compatible.")
        username.fill(settings.username)
        password.fill(settings.password)
        submit.click()
        if _is_blocked(page):
            return LoginResult(
                "blocked", "El login requiere CAPTCHA o MFA; se detiene sin intentar evitarlo."
            )
        if page.url != settings.login_url or _has_success_marker(page):
            return LoginResult("success", "Login completado correctamente.")
        return LoginResult("failed", "El login no pudo confirmarse.")
    finally:
        _close_resources(context, browser)


def login_with_playwright(settings: AdamsLoginSettings) -> LoginResult:
    """Run one attempt with Playwright's ephemeral browser context."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        return perform_login(settings, browser_api=playwright)


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ValueError(f"Falta la variable de configuración {name}.")
    return value


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("ADAMS_LOGIN_URL debe ser una URL HTTP(S) válida.")


def _goto(page: Any, url: str, timeout_seconds: int) -> None:
    """Use Playwright's timeout while keeping small synthetic fakes compatible."""
    try:
        page.goto(url, timeout=timeout_seconds * 1000)
    except TypeError:
        page.goto(url)


def _close_resources(context: Any | None, browser: Any | None) -> None:
    """Close partially acquired resources without masking the original error."""
    if context is not None:
        with suppress(Exception):
            context.close()
    if browser is not None:
        with suppress(Exception):
            browser.close()


def _first_visible(page: Any, selectors: tuple[str, ...]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.is_visible():
            return locator
    return None


def _first_value(page: Any, field_name: str) -> str | None:
    """Read one transient hidden form value without exposing it to callers."""
    try:
        locator = page.locator(f"input[name='{field_name}']").first
        if locator.count() == 0:
            return None
        value = locator.input_value()
    except (AttributeError, TypeError, ValueError):
        return None
    return value if isinstance(value, str) and value else None


def _is_blocked(page: Any) -> bool:
    text = page.locator("body").inner_text().lower()
    return any(
        marker in text
        for marker in (
            "captcha",
            "recaptcha",
            "two-factor",
            "mfa",
            "autenticación multifactor",
            "intervención requerida",
            "intervention required",
        )
    )


def _has_success_marker(page: Any) -> bool:
    text = page.locator("body").inner_text().lower()
    return any(marker in text for marker in ("cerrar sesión", "logout", "bienvenido", "dashboard"))
