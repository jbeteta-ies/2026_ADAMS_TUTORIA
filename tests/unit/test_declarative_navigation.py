from __future__ import annotations

from threading import Event

import pytest

from adams_tutoria.declarative_navigation import (
    ExpectedResult,
    NavigationError,
    NavigationExecutor,
    NavigationPlan,
    NavigationPlanValidator,
    NavigationState,
    NavigationStatus,
    NavigationStep,
)


class Response:
    status = 200


class Locator:
    def __init__(self, value: str = "csrf-synthetic") -> None:
        self.value = value
        self.first = self

    def count(self) -> int:
        return 1

    def input_value(self) -> str:
        return self.value


class Body:
    def __init__(self, page: Page) -> None:
        self.page = page

    def inner_text(self) -> str:
        return self.page.body


class Page:
    def __init__(self) -> None:
        self.url = "https://synthetic.invalid/start"
        self.body = "Aula sintética"
        self.calls: list[dict[str, object]] = []

    def locator(self, selector: str) -> Locator | Body:
        return Body(self) if selector == "body" else Locator()

    def goto(self, url: str, **kwargs: object) -> Response:
        self.calls.append({"url": url, **kwargs})
        self.url = url
        return Response()


class Session:
    def __init__(self) -> None:
        self.page = Page()


def plan(*steps: NavigationStep) -> NavigationPlan:
    return NavigationPlan("1.0", tuple(steps), "https://synthetic.invalid")


def test_order_methods_params_form_and_expected_result() -> None:
    session = Session()
    result = NavigationExecutor(session).execute(
        plan(
            NavigationStep(
                1,
                "GET",
                "https://synthetic.invalid/room",
                {"course": "demo"},
                expected=ExpectedResult(url_path="/room"),
            ),
            NavigationStep(
                2,
                "POST",
                "https://synthetic.invalid/target",
                form_data={"choice": "synthetic", "csrf": "placeholder"},
                expected=ExpectedResult(status_code=200),
                read_only=True,
            ),
        )
    )
    assert [item.status for item in result] == [NavigationStatus.SUCCESS, NavigationStatus.SUCCESS]
    assert session.page.calls[0]["url"] == "https://synthetic.invalid/room?course=demo"
    assert session.page.calls[1]["method"] == "POST"
    assert session.page.calls[1]["post_data"] == "choice=synthetic&csrf=placeholder"


def test_csrf_field_is_read_from_current_page_without_logging_it() -> None:
    session = Session()
    result = NavigationExecutor(session).execute(
        plan(
            NavigationStep(
                1,
                "POST",
                "https://synthetic.invalid/next",
                {"tab": "one"},
                {"choice": "demo"},
                csrf_field="csrf",
                expected=ExpectedResult(status_code=200),
                read_only=True,
            )
        )
    )
    assert result[0].status is NavigationStatus.SUCCESS
    assert session.page.calls[0]["post_data"] == "choice=demo&csrf=csrf-synthetic"


@pytest.mark.parametrize(
    "body, status",
    [("captcha", NavigationStatus.BLOCKED), ("Iniciar sesión", NavigationStatus.SESSION_EXPIRED)],
)
def test_safety_stops_on_captcha_or_expired_session(body: str, status: NavigationStatus) -> None:
    session = Session()
    session.page.body = body
    executor = NavigationExecutor(session)
    result = executor.execute(
        plan(
            NavigationStep(
                1,
                "GET",
                "https://synthetic.invalid/target",
                expected=ExpectedResult(status_code=200),
            )
        )
    )
    assert result[0].status is status
    assert (
        executor.state is NavigationState.BLOCKED
        if status is NavigationStatus.BLOCKED
        else executor.state is NavigationState.FAILED
    )


def test_cancellation_is_cooperative() -> None:
    event = Event()
    event.set()
    result = NavigationExecutor(Session(), cancel_event=event).execute(
        plan(
            NavigationStep(
                1,
                "GET",
                "https://synthetic.invalid/target",
                expected=ExpectedResult(status_code=200),
            )
        )
    )
    assert result[0].status is NavigationStatus.CANCELLED


def test_validator_rejects_cross_origin_unbounded_timeout_and_unknown_method() -> None:
    validator = NavigationPlanValidator()
    with pytest.raises(NavigationError):
        validator.validate(plan(NavigationStep(1, "GET", "https://other.invalid/target")))
    with pytest.raises(NavigationError):
        validator.validate(plan(NavigationStep(1, "DELETE", "https://synthetic.invalid/target")))
    with pytest.raises(NavigationError):
        validator.validate(
            plan(NavigationStep(1, "GET", "https://synthetic.invalid/target", timeout_seconds=121))
        )


def test_validator_rejects_missing_expected_result_signal() -> None:
    with pytest.raises(NavigationError, match="señal"):
        NavigationPlanValidator().validate(
            plan(NavigationStep(1, "GET", "https://synthetic.invalid/target"))
        )


def test_validator_rejects_post_without_explicit_read_only_authorization() -> None:
    with pytest.raises(NavigationError, match="read_only"):
        NavigationPlanValidator().validate(
            plan(
                NavigationStep(
                    1,
                    "POST",
                    "https://synthetic.invalid/target",
                    form_data={"choice": "synthetic"},
                    expected=ExpectedResult(status_code=200),
                )
            )
        )


def test_hidden_csrf_field_is_accepted_without_visibility_check() -> None:
    session = Session()
    result = NavigationExecutor(session).execute(
        plan(
            NavigationStep(
                1,
                "POST",
                "https://synthetic.invalid/next",
                form_data={"choice": "demo"},
                csrf_field="csrf",
                expected=ExpectedResult(url_path="/next"),
                read_only=True,
            )
        )
    )
    assert result[0].status is NavigationStatus.SUCCESS


def test_external_redirect_is_rejected_even_when_response_is_successful() -> None:
    class RedirectResponse:
        status = 200
        url = "https://external.invalid/landing"

    session = Session()
    session.page.goto = lambda url, **kwargs: RedirectResponse()  # type: ignore[assignment]
    result = NavigationExecutor(session).execute(
        plan(
            NavigationStep(
                1,
                "GET",
                "https://synthetic.invalid/target",
                expected=ExpectedResult(status_code=200),
            )
        )
    )
    assert result[0].code == "external_redirect"


def test_expected_result_mismatch_fails() -> None:
    session = Session()
    session.page.body = "Unexpected synthetic page"
    result = NavigationExecutor(session).execute(
        plan(
            NavigationStep(
                1,
                "GET",
                "https://synthetic.invalid/target",
                expected=ExpectedResult(text_marker="Required synthetic marker"),
            )
        )
    )
    assert result[0].status is NavigationStatus.FAILED


def test_real_timeout_is_reported() -> None:
    class TimeoutPage(Page):
        def goto(self, url: str, **kwargs: object) -> Response:
            raise TimeoutError("synthetic timeout")

    session = Session()
    session.page = TimeoutPage()
    result = NavigationExecutor(session).execute(
        plan(
            NavigationStep(
                1,
                "GET",
                "https://synthetic.invalid/target",
                expected=ExpectedResult(status_code=200),
            )
        )
    )
    assert result[0].code == "timeout"
