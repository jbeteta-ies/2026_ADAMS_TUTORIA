"""Synthetic tests for provider login selection and safe outcomes."""

from __future__ import annotations

import pytest

from adams_tutoria.config import SiteConfig
from adams_tutoria.login_adapters import (
    AdamsLoginAdapter,
    LoginRequest,
    LoginStatus,
    UnimplementedLoginAdapter,
    UnknownProviderError,
    adapter_for_provider,
    adapter_for_site,
    request_from_site,
)


class Locator:
    def __init__(self, *, visible: bool = True) -> None:
        self.first = self
        self.visible = visible
        self.value = None

    def is_visible(self) -> bool:
        return self.visible

    def fill(self, value: str) -> None:
        self.value = value

    def click(self) -> None:
        return None

    def inner_text(self) -> str:
        return ""


class Page:
    url = "https://example.invalid/login"

    def __init__(self, body: str = "Logout") -> None:
        self.body = body
        self.fields = {
            "input[name='nombre']": Locator(),
            "input[name='clave']": Locator(),
            "button[name='Submit']": Locator(),
        }

    def goto(self, url: str) -> None:
        self.url = url

    def locator(self, selector: str) -> Locator:
        if selector == "body":
            return LocatorWithText(self.body)
        return self.fields.get(selector, Locator(visible=False))


class LocatorWithText(Locator):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def inner_text(self) -> str:
        return self.text


class Context:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.closed = False

    def new_page(self) -> Page:
        return self.page

    def close(self) -> None:
        self.closed = True


class Browser:
    def __init__(self, context: Context) -> None:
        self.context = context
        self.closed = False

    def new_context(self) -> Context:
        return self.context

    def close(self) -> None:
        self.closed = True


class BrowserApi:
    def __init__(self, page: Page) -> None:
        self.browser = Browser(Context(page))
        self.chromium = type("Chromium", (), {"launch": lambda _: self.browser})()


def request() -> LoginRequest:
    return LoginRequest("synthetic-user", "synthetic-password", "https://example.invalid/login")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Logout", LoginStatus.SUCCESS),
        ("", LoginStatus.FAILED),
        ("MFA required", LoginStatus.BLOCKED),
    ],
)
def test_adams_adapter_maps_outcomes_and_closes_resources(body: str, expected: LoginStatus) -> None:
    page = Page(body)
    api = BrowserApi(page)

    outcome = AdamsLoginAdapter().login(request(), browser_api=api)

    assert outcome.status is expected
    assert api.browser.context.closed and api.browser.closed
    assert "synthetic-password" not in outcome.message


def test_provider_selection_includes_adams_and_future_beta() -> None:
    assert isinstance(adapter_for_provider("adams"), AdamsLoginAdapter)
    assert isinstance(adapter_for_provider("BETA"), UnimplementedLoginAdapter)
    assert isinstance(adapter_for_site(_site()), UnimplementedLoginAdapter)


def test_unknown_provider_is_safe() -> None:
    with pytest.raises(UnknownProviderError, match="desconocido"):
        adapter_for_provider("PRIVATE-PROVIDER")


def test_site_request_is_immutable_and_does_not_change_config() -> None:
    site = _site()
    login_request = request_from_site(site)
    assert login_request.username == "synthetic-user"
    with pytest.raises(AttributeError):
        login_request.username = "changed"  # type: ignore[misc]


def _site() -> SiteConfig:
    return SiteConfig(
        "synthetic-site",
        "BETA",
        "https://example.invalid/login",
        "https://example.invalid/target",
        "synthetic-user",
        "synthetic-password",
    )
