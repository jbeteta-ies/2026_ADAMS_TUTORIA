"""Tests for the persistence-backed dashboard boundary."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from adams_tutoria.config import default_config
from adams_tutoria.dashboard import (
    _dashboard_request,
    _operational_summaries,
    _record_key,
    editions_for_course,
)
from adams_tutoria.demo_summary import demo_enrollment_summaries
from adams_tutoria.domain import (
    ContentNode,
    ContentNodeType,
    Course,
    Edition,
    Enrollment,
    ProgressSnapshot,
    Student,
)
from adams_tutoria.generation import HttpResponse
from adams_tutoria.ollama import OllamaSettings, OllamaSettingsRepository
from adams_tutoria.persistence.database import connection, database_path, initialize_database
from adams_tutoria.persistence.repositories import (
    ContentNodeRepository,
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    ProgressSnapshotRepository,
    StudentRepository,
)


def _seed_dashboard_database(tmp_path: Path) -> Path:
    """Create a completely synthetic operational catalog for AppTest."""
    config = default_config(base_dir=tmp_path)
    path = database_path(config)
    initialize_database(path)
    course = Course(uuid4(), "Curso sintético", "SYN-APP")
    edition = Edition(
        uuid4(), course, "Edición sintética", "edition-app", date(2026, 1, 1), date(2026, 6, 1)
    )
    student = Student(uuid4(), "Alumno sintético", "alumno@example.invalid", "student-app")
    enrollment = Enrollment(uuid4(), student, edition, "enrollment-app")
    CourseRepository(path).save(course)
    EditionRepository(path).save(edition)
    StudentRepository(path).save(student)
    EnrollmentRepository(path).save(enrollment)
    ProgressSnapshotRepository(path).save(
        ProgressSnapshot(uuid4(), enrollment, datetime(2026, 2, 1, tzinfo=UTC), Decimal("0"))
    )
    return path


def test_empty_operational_database_renders_without_synthetic_options(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()

    assert not app.exception
    assert any("No hay un curso" in item.value for item in app.info)
    assert not app.sidebar.selectbox


def test_populated_operational_database_renders_from_sqlite_with_app_test(tmp_path, monkeypatch):
    _seed_dashboard_database(tmp_path)
    monkeypatch.setenv("ADAMS_TUTORIA_BASE_DIR", str(tmp_path))
    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    assert not app.exception
    assert len(app.sidebar.selectbox) == 2
    assert len(app.sidebar.selectbox[0].options) == 1
    assert len(app.sidebar.selectbox[1].options) == 1

    app.sidebar.radio[0].set_value("Edición").run()
    assert not app.exception
    assert any("Contexto de la edición" in item.value for item in app.subheader)
    assert any("Recomendaciones de comunicación" in item.value for item in app.subheader)
    assert any("Borradores asistidos" in item.value for item in app.subheader)


def test_dashboard_reads_current_progress_contract_and_shows_coverage(tmp_path, monkeypatch):
    path = _seed_dashboard_database(tmp_path)
    imported_at = datetime(2026, 2, 15, tzinfo=UTC)
    with connection(path) as db:
        enrollment_id = db.execute("SELECT id FROM enrollment").fetchone()["id"]
        db.execute("DELETE FROM progress_snapshot")
        db.execute(
            "INSERT INTO enrollment_progress_current VALUES(?,?,?)",
            (enrollment_id, "75", imported_at.isoformat()),
        )
    monkeypatch.setenv("ADAMS_TUTORIA_BASE_DIR", str(tmp_path))
    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    app.sidebar.radio[0].set_value("Edición").run()

    assert not app.exception
    assert not app.error
    with connection(path) as db:
        edition_id = UUID(db.execute("SELECT id FROM edition").fetchone()["id"])
    summaries, _, metadata = _operational_summaries(edition_id, default_config(base_dir=tmp_path))
    assert summaries[0].progress.percentage == Decimal("75")
    assert metadata is not None and metadata[4]["con progreso"] == 1


def test_dashboard_projects_and_represents_content_progress_without_evaluations(
    tmp_path, monkeypatch
):
    path = _seed_dashboard_database(tmp_path)
    with connection(path) as db:
        enrollment_id = db.execute("SELECT id FROM enrollment").fetchone()["id"]
        edition_id = db.execute("SELECT id FROM edition").fetchone()["id"]
        course_id = db.execute("SELECT course_id FROM edition").fetchone()["course_id"]
    course = CourseRepository(path).get(UUID(course_id))
    edition = EditionRepository(path).get(UUID(edition_id))
    assert course is not None
    assert edition is not None
    node = ContentNode(
        uuid4(),
        course,
        edition,
        ContentNodeType.MODULE,
        "Contenido sintético",
    )
    ContentNodeRepository(path).save(node)
    with connection(path) as db:
        db.execute(
            "INSERT INTO content_progress_current VALUES(?,?,?,?)",
            (enrollment_id, str(node.id), "42", datetime(2026, 2, 20, tzinfo=UTC).isoformat()),
        )
    monkeypatch.setenv("ADAMS_TUTORIA_BASE_DIR", str(tmp_path))
    summaries, _, metadata = _operational_summaries(
        UUID(edition_id), default_config(base_dir=tmp_path)
    )
    assert summaries[0].progress.percentage == Decimal("0")
    assert metadata is not None
    assert metadata[4]["con evaluaciones"] == 0
    assert metadata[4]["con progreso por contenido"] == 1
    assert metadata[5][0].node.title == "Contenido sintético"
    assert metadata[5][0].progress_percentage == Decimal("42")


class _AppTransport:
    """Synthetic loopback transport used by AppTest; never opens a socket."""

    def __init__(
        self, response: bytes = b'{"model":"synthetic-effective","response":"Draft reviewed"}'
    ):
        self.response = response
        self.calls: list[tuple[str, bytes]] = []

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        del timeout_seconds
        self.calls.append((url, b""))
        return HttpResponse(200, b'{"models":[{"name":"synthetic-model"}]}')

    def post(self, url: str, body: bytes, timeout_seconds: float) -> HttpResponse:
        del timeout_seconds
        self.calls.append((url, body))
        return HttpResponse(200, self.response)


def test_apptest_generates_from_recommendation_and_exposes_review_controls(tmp_path, monkeypatch):
    path = _seed_dashboard_database(tmp_path)
    OllamaSettingsRepository(path).save(OllamaSettings("synthetic-model"))
    monkeypatch.setenv("ADAMS_TUTORIA_BASE_DIR", str(tmp_path))
    from streamlit.testing.v1 import AppTest

    transport = _AppTransport()
    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path)
    app.session_state["_ollama_transport"] = transport
    app.run()
    app.sidebar.radio[0].set_value("Edición").run()

    assert not app.exception
    assert app.multiselect
    assert app.multiselect[0].options
    app.multiselect[0].set_value([app.multiselect[0].options[0]])
    app.run()
    assert any("Vista previa del payload minimizado" in item.value for item in app.subheader)
    assert app.json
    next(
        button for button in app.button if button.label == "Generar borradores seleccionados"
    ).click().run()
    assert not app.exception
    assert not app.error, [item.value for item in app.error]
    assert any(item.label == "Borrador" for item in app.text_area)
    assert any(url.endswith("/api/generate") for url, _ in transport.calls)


def test_settings_reports_discovery_failure_without_blocking_dashboard(tmp_path, monkeypatch):
    _seed_dashboard_database(tmp_path)
    monkeypatch.setenv("ADAMS_TUTORIA_BASE_DIR", str(tmp_path))
    from streamlit.testing.v1 import AppTest

    class FailingTransport(_AppTransport):
        def get(self, url: str, timeout_seconds: float) -> HttpResponse:
            raise OSError("synthetic unavailable")

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path)
    app.session_state["_ollama_transport"] = FailingTransport()
    app.run()
    app.sidebar.radio[0].set_value("Settings").run()
    app.button(key="ollama-list").click().run()

    assert not app.exception
    assert any("No se pudieron listar los modelos" in item.value for item in app.error)
    app.sidebar.radio[0].set_value("Edición").run()
    assert not app.exception


def test_settings_page_is_available_even_when_operational_database_is_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from streamlit.testing.v1 import AppTest

    dashboard_path = Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py"
    app = AppTest.from_file(dashboard_path).run()
    app.sidebar.radio[0].set_value("Settings").run()
    assert not app.exception
    assert app.title[0].value == "Settings"
    assert any("localhost" in item.value for item in app.caption)


def test_selection_helper_does_not_fabricate_unknown_course(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert editions_for_course(str(uuid4())) == ()


def test_dashboard_request_is_one_enrollment_and_minimized() -> None:
    summary = demo_enrollment_summaries("edition-alpha-2026-1")[0]
    request = _dashboard_request(summary, "seguimiento", "Mantén tono neutral")

    assert request.enrollment.id == summary.enrollment_id
    assert request.communication_type == "seguimiento"
    assert "student_name" not in request.prompt.as_mapping()
    assert "student_email" not in request.prompt.as_mapping()
    assert request.prompt.context.as_mapping()["follow_up_reasons"]


def test_dashboard_record_state_key_isolated_by_edition_and_enrollment() -> None:
    enrollment = demo_enrollment_summaries("edition-alpha-2026-1")[0].enrollment_id
    assert _record_key("edition-alpha-2026-1", enrollment) != _record_key(
        "edition-alpha-2026-2", enrollment
    )


def test_dashboard_source_has_no_demo_profile_writes() -> None:
    source = (Path(__file__).parents[2] / "src/adams_tutoria/dashboard.py").read_text()
    assert "demo_profile" not in source
    assert ".save(profile" not in source
