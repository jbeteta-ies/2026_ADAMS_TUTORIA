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
