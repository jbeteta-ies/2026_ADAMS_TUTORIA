"""Tests for the synthetic Streamlit dashboard shell."""

from pathlib import Path

from adams_tutoria.dashboard import (
    COURSES,
    EDITIONS,
    _dashboard_request,
    _record_key,
    editions_for_course,
)
from adams_tutoria.demo_summary import demo_enrollment_summaries


def test_streamlit_shell_renders_with_apptest():
    """The dashboard starts in Streamlit's supported headless test harness."""

    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()

    assert not app.exception
    assert app.sidebar.selectbox[0].label == "Curso"
    assert app.sidebar.selectbox[1].label == "Edición"


def test_edition_page_shows_exactly_six_metrics_and_values() -> None:
    """The edition placeholder is replaced by the six required indicators."""

    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    app.sidebar.radio[0].set_value("Edición").run()

    assert [metric.label for metric in app.metric] == [
        "Total",
        "No iniciados",
        "Inactivos",
        "Evaluaciones pendientes",
        "Finalizados",
        "Requieren atención",
    ]
    assert [metric.value for metric in app.metric] == ["2", "1", "1", "2", "0", "2"]


def test_question_assistant_shows_manual_draft_and_reference() -> None:
    """The dashboard exposes a synthetic, traceable draft without sending it."""

    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    app.text_input[0].set_value("planificación tareas")
    app.button[0].click().run()

    assert not app.exception
    assert any(widget.label == "Borrador (revisión manual)" for widget in app.text_area)
    assert any("tema-uno.md" in widget.value for widget in app.caption)


def test_changing_edition_is_isolated() -> None:
    """Changing the selector recomputes only the selected synthetic edition."""

    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    app.sidebar.radio[0].set_value("Edición").run()
    app.sidebar.selectbox[1].set_value("edition-alpha-2026-2").run()

    assert [metric.value for metric in app.metric] == ["1", "0", "0", "0", "1", "0"]


def test_beta_enrollment_without_follow_up_reasons_renders_profile() -> None:
    """The Beta profile remains usable when no follow-up communication is suggested."""

    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    app.sidebar.radio[0].set_value("Edición").run()
    app.sidebar.selectbox[0].set_value("course-demo-beta").run()
    app.sidebar.selectbox[1].set_value("edition-beta-2026-1").run()
    app.selectbox[-1].set_value(app.selectbox[-1].options[0]).run()

    assert not app.exception
    assert app.subheader[-1].value == "Ficha de alumno"


def test_message_requires_approval_before_it_is_visible(tmp_path, monkeypatch) -> None:
    """The synthetic message is gated by an explicit tutor approval."""

    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    app.sidebar.radio[0].set_value("Edición").run()
    app.selectbox[-1].set_value(app.selectbox[-1].options[0]).run()

    assert not [widget for widget in app.text_area if widget.label.startswith("Mensaje")]
    approve = next(
        button for button in app.button if button.label == "Aprobar mensaje para revisión"
    )

    approve.click().run()
    messages = [widget for widget in app.text_area if widget.label.startswith("Mensaje")]
    assert len(messages) == 1
    message = messages[0].value
    assert message is not None
    assert "Alumno sintético" in message
    assert any(button.label.startswith("Registrar COPIED") for button in app.button)
    assert any(button.label.startswith("Descargar mensaje") for button in app.download_button)


def test_dashboard_demo_source_contains_no_operational_data_access() -> None:
    """The demo provider remains synthetic and privacy-safe."""

    source = (Path(__file__).parents[2] / "src/adams_tutoria/demo_summary.py").read_text()
    assert "sqlite" not in source.lower()
    assert "email" not in source.lower()
    assert "adams export" not in source.lower()


def test_course_and_edition_ids_are_stable_and_unique():
    """Catalog identifiers are explicit and unique."""

    assert len({course.id for course in COURSES}) == len(COURSES)
    assert len({edition.id for edition in EDITIONS}) == len(EDITIONS)


def test_editions_are_filtered_by_course():
    """The pure catalog function returns only editions for the selected course."""

    assert [edition.id for edition in editions_for_course("course-demo-alpha")] == [
        "edition-alpha-2026-1",
        "edition-alpha-2026-2",
    ]
    assert all(
        edition.course_id == "course-demo-beta"
        for edition in editions_for_course("course-demo-beta")
    )


def test_unknown_course_has_no_editions():
    """Unknown selections do not expose unrelated editions."""

    assert editions_for_course("unknown-course") == ()


def test_dashboard_request_is_one_enrollment_and_minimized() -> None:
    """The UI request carries one synthetic enrollment and no identity payload."""
    summary = demo_enrollment_summaries("edition-alpha-2026-1")[0]
    request = _dashboard_request(summary, "seguimiento", "Mantén tono neutral")

    assert request.enrollment.id == summary.enrollment_id
    assert request.communication_type == "seguimiento"
    assert "student_name" not in request.prompt.as_mapping()
    assert "student_email" not in request.prompt.as_mapping()
    assert request.prompt.context.as_mapping()["follow_up_reasons"]


def test_dashboard_record_state_key_isolated_by_edition_and_enrollment() -> None:
    """Draft widget state cannot collide across editions or enrollments."""
    enrollment = demo_enrollment_summaries("edition-alpha-2026-1")[0].enrollment_id

    assert _record_key("edition-alpha-2026-1", enrollment) != _record_key(
        "edition-alpha-2026-2", enrollment
    )
    assert _record_key("edition-alpha-2026-1", enrollment) != _record_key(
        "edition-alpha-2026-1", demo_enrollment_summaries("edition-alpha-2026-1")[1].enrollment_id
    )
