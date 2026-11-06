"""Synthetic tests for provider login selection and safe outcomes."""

from __future__ import annotations

import pytest

from adams_tutoria.config import SiteConfig
from adams_tutoria.declarative_navigation import (
    ExpectedResult,
    NavigationExecutor,
    NavigationPlan,
    NavigationStep,
)
from adams_tutoria.login_adapters import (
    AdamsLoginAdapter,
    LoginRequest,
    LoginStatus,
    MantiaLoginAdapter,
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

    def count(self) -> int:
        return int(self.visible)

    def input_value(self) -> str:
        return "token-synthetic"


class Page:
    url = "https://example.invalid/login"

    def __init__(self, body: str = "Logout") -> None:
        self.body = body
        self.submitted: dict[str, str] = {}
        self.fields = {
            "input[name='nombre']": Locator(),
            "input[name='clave']": Locator(),
            "input[name='logintoken']": Locator(),
        }

    def goto(self, url: str) -> None:
        self.url = url

    def locator(self, selector: str) -> Locator:
        if selector == "body":
            return LocatorWithText(self.body)
        if selector == "button[name='Submit']":
            return SubmitLocator(self)
        return self.fields.get(selector, Locator(visible=False))


class LocatorWithText(Locator):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def inner_text(self) -> str:
        return self.text


class SubmitLocator(Locator):
    def __init__(self, page: Page) -> None:
        super().__init__()
        self.page = page

    def click(self) -> None:
        self.page.submitted = {
            "username": self.page.fields["input[name='nombre']"].value or "",
            "password": self.page.fields["input[name='clave']"].value or "",
            "logintoken": self.page.fields["input[name='logintoken']"].input_value(),
        }


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
    assert isinstance(adapter_for_provider("mantia"), MantiaLoginAdapter)
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


def test_mantia_extracts_token_in_memory_and_closes_session() -> None:
    page = Page("Logout")
    api = BrowserApi(page)

    outcome = MantiaLoginAdapter().login(request(), browser_api=api)

    assert outcome.status is LoginStatus.SUCCESS
    assert page.submitted["logintoken"] == "token-synthetic"
    assert api.browser.context.closed and api.browser.closed


def test_mantia_rejects_login_form_without_runtime_token() -> None:
    page = Page("Logout")
    page.fields.pop("input[name='logintoken']")
    api = BrowserApi(page)

    outcome = MantiaLoginAdapter().login(request(), browser_api=api)

    assert outcome.status is LoginStatus.FAILED
    assert api.browser.context.closed and api.browser.closed


def test_mantia_monitor_uses_authenticated_get_urls_in_order() -> None:
    urls = (
        "https://betaformacion.mantia.es/my/",
        "https://betaformacion.mantia.es/course/view.php?id=56",
        "https://betaformacion.mantia.es/mod/forum/view.php?id=3834",
        "https://betaformacion.mantia.es/mod/scorm/view.php?id=3838",
    )
    page = MonitoringPage()
    session = type("AuthenticatedSession", (), {"page": page})()
    plan = NavigationPlan(
        "1.0",
        tuple(
            NavigationStep(
                index,
                "GET",
                url,
                expected=ExpectedResult(
                    status_code=200, url_path=url.split(".es", 1)[1].split("?", 1)[0]
                ),
            )
            for index, url in enumerate(urls, start=1)
        ),
        "https://betaformacion.mantia.es",
    )

    diagnostics = NavigationExecutor(session).execute(plan)

    assert [diagnostic.status.value for diagnostic in diagnostics] == ["success"] * 4
    assert page.requests == list(urls)
    assert page.cookie_jar == {"MoodleSession": "synthetic-session"}


def _site() -> SiteConfig:
    return SiteConfig(
        "synthetic-site",
        "BETA",
        "https://example.invalid/login",
        "https://example.invalid/target",
        "synthetic-user",
        "synthetic-password",
    )


class MonitoringPage:
    """Synthetic authenticated page; cookies never leave this test object."""

    def __init__(self) -> None:
        self.url = "https://betaformacion.mantia.es/my/"
        self.requests: list[str] = []
        self.cookie_jar = {"MoodleSession": "synthetic-session"}

    def goto(self, url: str, *, timeout: int) -> MonitoringResponse:
        del timeout
        self.requests.append(url)
        self.url = url
        return MonitoringResponse(url)

    def locator(self, selector: str) -> MonitoringBody:
        assert selector == "body"
        return MonitoringBody("Área personal autenticada")


class MonitoringResponse:
    def __init__(self, url: str) -> None:
        self.url = url
        self.status = 200


class MonitoringBody:
    def __init__(self, text: str) -> None:
        self.text = text

    def inner_text(self) -> str:
        return self.text
