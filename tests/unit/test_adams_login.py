from pathlib import Path

import pytest

from adams_tutoria.adams_login import AdamsLoginSettings, perform_login


class Locator:
    def __init__(self, *, text: str = "", visible: bool = True) -> None:
        self.first = self
        self.text = text
        self.visible = visible
        self.value: str | None = None
        self.clicked = False

    def is_visible(self) -> bool:
        return self.visible

    def fill(self, value: str) -> None:
        self.value = value

    def click(self) -> None:
        self.clicked = True

    def inner_text(self) -> str:
        return self.text


class Page:
    def __init__(self, body: str = "") -> None:
        self.body = body
        self.url = "https://example.invalid/login"
        self.locators: dict[str, Locator] = {}

    def goto(self, url: str) -> None:
        self.url = url

    def locator(self, selector: str) -> Locator:
        return self.locators.setdefault(selector, Locator(text=self.body, visible=False))


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


class Chromium:
    def __init__(self, browser: Browser) -> None:
        self.browser = browser

    def launch(self) -> Browser:
        return self.browser


class BrowserApi:
    def __init__(self, page: Page) -> None:
        self.browser = Browser(Context(page))
        self.chromium = Chromium(self.browser)


def configured() -> AdamsLoginSettings:
    return AdamsLoginSettings(
        "synthetic-user", "synthetic-password", "https://example.invalid/login"
    )


def prepare_page(body: str = "") -> tuple[Page, BrowserApi]:
    page = Page(body)
    page.locators["input[name='nombre']"] = Locator()
    page.locators["input[name='clave']"] = Locator()
    page.locators["button[name='Submit']"] = Locator()
    return page, BrowserApi(page)


def test_env_file_loads_all_documented_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ADAMS_USERNAME=synthetic-user\nADAMS_PASSWORD=synthetic-password\n"
        "ADAMS_LOGIN_URL=https://example.invalid/login\nADAMS_TARGET_URL=https://example.invalid/target\n"
        "ADAMS_INTERVAL_SECONDS=42\n",
        encoding="utf-8",
    )
    values = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in env_file.read_text(encoding="utf-8").splitlines()
    }
    result = AdamsLoginSettings.from_environment(environ=values)
    assert result.username == "synthetic-user"
    assert result.target_url == "" and result.interval_seconds == 300


def test_success_closes_context_and_does_not_store_session() -> None:
    page, api = prepare_page("Logout")
    result = perform_login(configured(), browser_api=api)
    assert result.status == "success"
    assert api.browser.context.closed and api.browser.closed
    assert page.locators["input[name='clave']"].value == "synthetic-password"


def test_real_login_fields_are_detected_when_submit_is_outside_form() -> None:
    page, api = prepare_page("Logout")

    result = perform_login(configured(), browser_api=api)

    assert result.status == "success"
    assert page.locators["input[name='nombre']"].value == "synthetic-user"
    assert page.locators["input[name='clave']"].value == "synthetic-password"
    assert page.locators["button[name='Submit']"].clicked


def test_captcha_is_blocked_without_bypass() -> None:
    page, api = prepare_page("CAPTCHA required")
    result = perform_login(configured(), browser_api=api)
    assert result.status == "blocked"
    assert "CAPTCHA" in result.message
    assert api.browser.context.closed and api.browser.closed


def test_missing_password_is_rejected() -> None:
    with pytest.raises(ValueError, match="ADAMS_PASSWORD"):
        AdamsLoginSettings.from_environment(
            environ={
                "ADAMS_USERNAME": "synthetic-user",
                "ADAMS_LOGIN_URL": "https://example.invalid",
            }
        )
