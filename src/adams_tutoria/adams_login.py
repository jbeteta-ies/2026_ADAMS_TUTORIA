"""One-shot, non-persistent browser login prototype for ADAMS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
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

    @classmethod
    def from_environment(
        cls, environ: dict[str, str] | None = None, *, env_file: Path | None = None
    ) -> AdamsLoginSettings:
        values = _read_env_file(env_file) if env_file else {}
        values.update(os.environ if environ is None else environ)
        return cls(
            _required(values, "ADAMS_USERNAME"),
            _required(values, "ADAMS_PASSWORD"),
            _required(values, "ADAMS_LOGIN_URL"),
        )


@dataclass(frozen=True)
class LoginResult:
    status: str
    message: str


def perform_login(settings: AdamsLoginSettings, *, browser_api: Any) -> LoginResult:
    """Submit one login attempt using an injected Playwright-like API."""
    _validate_url(settings.login_url)
    browser = browser_api.chromium.launch()
    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto(settings.login_url)
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
        context.close()
        browser.close()


def login_with_playwright(settings: AdamsLoginSettings) -> LoginResult:
    """Run one attempt with Playwright's ephemeral browser context."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        return perform_login(settings, browser_api=playwright)


def _required(values: dict[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ValueError(f"Falta la variable de configuración {name}.")
    return value


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("ADAMS_LOGIN_URL debe ser una URL HTTP(S) válida.")


def _first_visible(page: Any, selectors: tuple[str, ...]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.is_visible():
            return locator
    return None


def _is_blocked(page: Any) -> bool:
    text = page.locator("body").inner_text().lower()
    return any(
        marker in text
        for marker in ("captcha", "recaptcha", "two-factor", "mfa", "autenticación multifactor")
    )


def _has_success_marker(page: Any) -> bool:
    text = page.locator("body").inner_text().lower()
    return any(marker in text for marker in ("cerrar sesión", "logout", "bienvenido", "dashboard"))
