"""Tests for the synthetic Streamlit dashboard shell."""

from pathlib import Path

from adams_tutoria.dashboard import COURSES, EDITIONS, editions_for_course


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
