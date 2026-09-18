"""Parity and behavior tests for SQLite persistence using synthetic data only."""

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.config import default_config
from adams_tutoria.domain import (
    CommunicationRecord,
    CommunicationStatus,
    ContentNode,
    ContentNodeType,
    ContentProgressSnapshot,
    ContentSource,
    ContentSourceType,
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationResultStatus,
    EvaluationStatus,
    EvaluationTargetType,
    ImportBatch,
    ImportBatchChange,
    ImportBatchStatus,
    ImportSourceType,
    ProgressSnapshot,
    Student,
    TutorAction,
)
from adams_tutoria.persistence.database import connection, database_path, initialize_database
from adams_tutoria.persistence.repositories import (
    CommunicationRecordRepository,
    ContentNodeRepository,
    ContentProgressSnapshotRepository,
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    EvaluationRepository,
    ImportBatchChangeRepository,
    ImportBatchRepository,
    ProgressSnapshotRepository,
    StudentRepository,
    TutorActionRepository,
)


def _graph() -> tuple[Course, Edition, Student, Enrollment]:
    course = Course(uuid4(), "Synthetic course", "SYN", "Synthetic description")
    edition = Edition(uuid4(), course, "Spring", "edition-x", date(2026, 1, 1), date(2026, 6, 1))
    student = Student(uuid4(), "Synthetic Student", "student@example.invalid", "student-x")
    enrollment = Enrollment(uuid4(), student, edition, "enrollment-x")
    return course, edition, student, enrollment


def _ready(path: Path) -> tuple[Course, Edition, Student, Enrollment]:
    initialize_database(path)
    values = _graph()
    CourseRepository(path).save(values[0])
    EditionRepository(path).save(values[1])
    StudentRepository(path).save(values[2])
    EnrollmentRepository(path).save(values[3])
    return values


def test_initialization_is_idempotent_and_has_all_tables(tmp_path: Path) -> None:
    path = tmp_path / "test.sqlite3"
    initialize_database(path)
    initialize_database(path)
    with connection(path) as db:
        names = {
            row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert names == {
            "course",
            "edition",
            "student",
            "enrollment",
            "progress_snapshot",
            "content_node",
            "content_progress_snapshot",
            "evaluation",
            "communication_record",
            "tutor_action",
            "import_batch",
            "import_batch_change",
            "student_external_identity",
            "enrollment_external_identity",
            "enrollment_state",
            "student_history",
            "enrollment_history",
            "evaluation_external_identity",
            "evaluation_history",
            "generation_record",
            "generation_transition",
            "generation_failure",
            "content_progress_current",
            "enrollment_progress_current",
        }
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connection_rolls_back_and_closes_transaction(tmp_path: Path) -> None:
    path = tmp_path / "transaction.sqlite3"
    initialize_database(path)
    with pytest.raises(RuntimeError), connection(path) as db:
        db.execute(
            "INSERT INTO course(id,name,code,description) VALUES(?,?,?,?)",
            ("rollback", "x", None, None),
        )
        raise RuntimeError("synthetic failure")
    with connection(path) as db:
        assert db.execute("SELECT * FROM course").fetchone() is None


def test_legacy_generation_record_is_migrated_additively(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE course (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT, description TEXT
            );
            CREATE TABLE edition (id TEXT PRIMARY KEY, course_id TEXT NOT NULL, label TEXT NOT NULL,
                                  external_id TEXT, start_date TEXT, end_date TEXT);
            CREATE TABLE student (
                id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT, external_id TEXT
            );
            CREATE TABLE enrollment (
                id TEXT PRIMARY KEY, student_id TEXT NOT NULL, edition_id TEXT NOT NULL,
                                     external_id TEXT);
            CREATE TABLE generation_record (
                id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL, communication_type TEXT NOT NULL,
                reason TEXT NOT NULL, model_payload TEXT NOT NULL, draft_text TEXT NOT NULL,
                created_at TEXT NOT NULL, status TEXT NOT NULL, reviewed_at TEXT, edited_at TEXT,
                copied_at TEXT, sent_at TEXT
            );
            """
        )
    initialize_database(path)
    with connection(path) as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(generation_record)")}
    assert {"draft_ref", "draft_hash", "error_code", "model_name", "prompt_version"} <= columns


def test_all_entities_round_trip_every_field_and_relationship(tmp_path: Path) -> None:
    path = tmp_path / "entities.sqlite3"
    course, edition, student, enrollment = _ready(path)
    assert CourseRepository(path).get(course.id) == course
    assert EditionRepository(path).get(edition.id) == edition
    assert StudentRepository(path).get(student.id) == student
    assert EnrollmentRepository(path).get(enrollment.id) == enrollment


def test_course_content_source_round_trip_and_reinitialization(tmp_path: Path) -> None:
    path = tmp_path / "content.sqlite3"
    initialize_database(path)
    source = ContentSource(ContentSourceType.LOCAL_PATH, "synthetic/content", "markdown", "r1")
    course = Course(uuid4(), "Synthetic course", content_source=source)
    CourseRepository(path).save(course)
    initialize_database(path)
    assert CourseRepository(path).get(course.id) == course


def test_all_entities_round_trip_continues_after_content_source_test(tmp_path: Path) -> None:
    path = tmp_path / "entities.sqlite3"
    course, edition, student, enrollment = _ready(path)
    assert CourseRepository(path).get(course.id) == course
    assert EditionRepository(path).get(edition.id) == edition
    assert StudentRepository(path).get(student.id) == student
    assert EnrollmentRepository(path).get(enrollment.id) == enrollment

    snapshot = ProgressSnapshot(
        uuid4(), enrollment, datetime(2026, 2, 1, 9, 30, tzinfo=UTC), Decimal("42.50"), "snapshot-x"
    )
    ProgressSnapshotRepository(path).save(snapshot)
    assert ProgressSnapshotRepository(path).get(snapshot.id) == snapshot

    evaluation = Evaluation(
        uuid4(),
        enrollment,
        EvaluationTargetType.ACTIVITY,
        "activity-x",
        EvaluationStatus.COMPLETED,
        Decimal("8.25"),
        Decimal("10.00"),
        False,
        datetime(2026, 2, 2, tzinfo=UTC),
        "Activity X",
        "evaluation-x",
    )
    EvaluationRepository(path).save(evaluation)
    assert EvaluationRepository(path).get(evaluation.id) == evaluation

    snapshot_none = ProgressSnapshot(
        uuid4(), enrollment, datetime(2026, 2, 6, tzinfo=UTC), Decimal("10")
    )
    ProgressSnapshotRepository(path).save(snapshot_none)
    assert ProgressSnapshotRepository(path).get(snapshot_none.id) == snapshot_none

    evaluation_none = Evaluation(
        uuid4(), enrollment, EvaluationTargetType.MODULE, "module", EvaluationStatus.COMPLETED
    )
    EvaluationRepository(path).save(evaluation_none)
    assert EvaluationRepository(path).get(evaluation_none.id) == evaluation_none

    communication = CommunicationRecord(
        uuid4(),
        enrollment,
        "check_in",
        "inactivity",
        datetime(2026, 2, 3, tzinfo=UTC),
        CommunicationStatus.SENT,
        datetime(2026, 2, 4, tzinfo=UTC),
        datetime(2026, 2, 5, tzinfo=UTC),
        "dedupe-x",
        "context-x",
    )
    CommunicationRecordRepository(path).save(communication)
    assert CommunicationRecordRepository(path).get(communication.id) == communication


def test_content_hierarchy_and_append_only_progress_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "content-hierarchy.sqlite3"
    course, edition, _, enrollment = _ready(path)
    module = ContentNode(uuid4(), course, edition, ContentNodeType.MODULE, "Synthetic module")
    submodule = ContentNode(
        uuid4(), course, edition, ContentNodeType.SUBMODULE, "Synthetic submodule", module
    )
    element = ContentNode(
        uuid4(), course, edition, ContentNodeType.ELEMENT, "Synthetic element", submodule
    )
    nodes = ContentNodeRepository(path)
    for node in (module, submodule, element):
        nodes.save(node)
    assert nodes.get(element.id) == element
    assert {node.id for node in nodes.list_for_edition(edition.id)} == {
        module.id,
        submodule.id,
        element.id,
    }

    snapshots = ContentProgressSnapshotRepository(path)
    first = ContentProgressSnapshot(
        uuid4(), enrollment, element, datetime(2026, 2, 1, tzinfo=UTC), Decimal("20")
    )
    second = ContentProgressSnapshot(
        uuid4(), enrollment, element, datetime(2026, 2, 2, tzinfo=UTC), Decimal("80")
    )
    snapshots.save(first)
    snapshots.save(second)
    assert snapshots.list_for_enrollment_and_node(enrollment.id, element.id) == (first, second)
    with pytest.raises(sqlite3.IntegrityError):
        snapshots.save(first)


def test_content_nodes_and_progress_reject_invalid_scope_and_percentage(tmp_path: Path) -> None:
    course, edition, student, enrollment = _graph()
    other_edition = Edition(uuid4(), course, "Other")
    module = ContentNode(uuid4(), course, edition, ContentNodeType.MODULE, "Synthetic module")
    with pytest.raises(ValueError):
        ContentNode(uuid4(), course, edition, ContentNodeType.ELEMENT, "Synthetic element")
    with pytest.raises(ValueError):
        ContentNode(
            uuid4(), course, other_edition, ContentNodeType.SUBMODULE, "Synthetic submodule", module
        )
    with pytest.raises(ValueError):
        ContentProgressSnapshot(
            uuid4(), enrollment, module, datetime(2026, 2, 1, tzinfo=UTC), Decimal("NaN")
        )
    with pytest.raises(ValueError):
        ContentProgressSnapshot(
            uuid4(),
            Enrollment(uuid4(), student, other_edition),
            module,
            datetime(2026, 2, 1, tzinfo=UTC),
            Decimal("1"),
        )


def test_optionals_round_trip_as_none(tmp_path: Path) -> None:
    path = tmp_path / "none.sqlite3"
    course = Course(uuid4(), "Minimal")
    edition = Edition(uuid4(), course, "Edition")
    student = Student(uuid4(), "Student")
    enrollment = Enrollment(uuid4(), student, edition)
    initialize_database(path)
    CourseRepository(path).save(course)
    EditionRepository(path).save(edition)
    StudentRepository(path).save(student)
    EnrollmentRepository(path).save(enrollment)
    evaluation = Evaluation(
        uuid4(), enrollment, EvaluationTargetType.MODULE, "module", EvaluationStatus.COMPLETED
    )
    EvaluationRepository(path).save(evaluation)
    assert EvaluationRepository(path).get(evaluation.id) == evaluation


def test_evaluation_result_fields_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "evaluation-result.sqlite3"
    _, _, _, enrollment = _ready(path)
    evaluation = Evaluation(
        uuid4(),
        enrollment,
        EvaluationTargetType.ACTIVITY,
        "activity-result",
        EvaluationStatus.COMPLETED,
        result_status=EvaluationResultStatus.ATTEMPTED,
        raw_value=" 7.5 ",
        numeric_value=Decimal("7.5"),
        scale="points-10",
    )

    repository = EvaluationRepository(path)
    repository.save(evaluation)

    restored = repository.get(evaluation.id)
    assert restored is not None
    assert restored.result_status is EvaluationResultStatus.ATTEMPTED
    assert restored.raw_value == " 7.5 "
    assert restored.numeric_value == Decimal("7.5")
    assert restored.scale == "points-10"


def test_snapshot_is_insert_only_and_upserts_evaluation_and_communication(tmp_path: Path) -> None:
    path = tmp_path / "semantics.sqlite3"
    _, _, _, enrollment = _ready(path)
    snapshot = ProgressSnapshot(uuid4(), enrollment, datetime(2026, 1, 1, tzinfo=UTC), Decimal("1"))
    repo = ProgressSnapshotRepository(path)
    repo.save(snapshot)
    with pytest.raises(sqlite3.IntegrityError):
        repo.save(snapshot)

    evaluation = Evaluation(uuid4(), enrollment, EvaluationTargetType.MODULE, "m")
    evaluations = EvaluationRepository(path)
    evaluations.save(evaluation)
    updated = Evaluation(evaluation.id, enrollment, EvaluationTargetType.MODULE, "m2")
    evaluations.save(updated)
    assert evaluations.get(evaluation.id) == updated

    communication = CommunicationRecord(
        uuid4(),
        enrollment,
        "check",
        "reason",
        datetime(2026, 1, 1, tzinfo=UTC),
        deduplication_key="k",
    )
    communications = CommunicationRecordRepository(path)
    communications.save(communication)
    assert communications.get(communication.id) == communication


def test_operational_path_is_not_touched_by_persistence_tests(tmp_path: Path) -> None:
    config = default_config(base_dir=tmp_path)
    assert database_path(config) == tmp_path / "data" / "local" / "adams_tutoria.sqlite3"
    assert not database_path(config).exists()


def test_tutor_actions_are_persisted_separately_and_scoped(tmp_path: Path) -> None:
    path = tmp_path / "actions.sqlite3"
    *_, enrollment = _ready(path)
    action = TutorActionRepository(path)
    value = TutorAction(
        uuid4(), enrollment.id, datetime(2026, 2, 1, tzinfo=UTC), "Revisar", "synthetic"
    )
    action.save(value)
    assert action.get(value.id) == value
    assert action.list_for_enrollment(enrollment.id) == (value,)


def test_tutor_actions_round_trip_does_not_leak_between_enrollments(tmp_path: Path) -> None:
    path = tmp_path / "scoped-actions.sqlite3"
    *_, enrollment = _ready(path)
    other = Enrollment(uuid4(), enrollment.student, enrollment.edition)
    EnrollmentRepository(path).save(other)
    repository = TutorActionRepository(path)
    first = TutorAction(uuid4(), enrollment.id, datetime(2026, 2, 1, tzinfo=UTC), "Primera")
    second = TutorAction(uuid4(), other.id, datetime(2026, 2, 2, tzinfo=UTC), "Segunda")

    repository.save(first)
    repository.save(second)

    assert repository.list_for_enrollment(enrollment.id) == (first,)
    assert repository.list_for_enrollment(other.id) == (second,)


def test_import_batch_round_trip_and_safe_change_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "imports.sqlite3"
    initialize_database(path)
    batch = ImportBatch(
        uuid4(),
        ImportSourceType.EXCEL,
        "synthetic-report.xlsx",
        datetime(2026, 3, 1, 10, tzinfo=UTC),
        source_reference="local-ref",
        source_fingerprint="a" * 64,
        context="edition-x",
        action="upsert",
        total_count=3,
        accepted_count=2,
        rejected_count=1,
        warning_count=1,
    )
    batches = ImportBatchRepository(path)
    batches.save(batch)
    assert batches.get(batch.id) == batch
    batches.transition(batch.id, ImportBatchStatus.CONFIRMED, datetime(2026, 3, 1, 11, tzinfo=UTC))
    batches.transition(batch.id, ImportBatchStatus.APPLIED, datetime(2026, 3, 1, 12, tzinfo=UTC))
    applied = batches.get(batch.id)
    assert applied is not None and applied.status is ImportBatchStatus.APPLIED
    change = ImportBatchChange(
        uuid4(),
        batch.id,
        "enrollment",
        "rejected",
        source_row_number=4,
        source_identifier="row-4",
        diagnostic_code="missing_evidence",
        diagnostic_message="Required evidence missing",
    )
    changes = ImportBatchChangeRepository(path)
    changes.save(change)
    assert changes.list_for_batch(batch.id) == (change,)
    with connection(path) as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(import_batch)")}
        assert (
            "source_name" in columns and "raw_row" not in columns and "source_file" not in columns
        )


def test_import_batch_transition_rejects_invalid_and_naive_values(tmp_path: Path) -> None:
    path = tmp_path / "import-transitions.sqlite3"
    initialize_database(path)
    batch = ImportBatch(
        uuid4(), ImportSourceType.MANUAL, "synthetic", datetime(2026, 3, 1, tzinfo=UTC)
    )
    repository = ImportBatchRepository(path)
    repository.save(batch)
    with pytest.raises(ValueError, match="timezone-aware"):
        repository.transition(batch.id, ImportBatchStatus.CONFIRMED, datetime(2026, 3, 1, 1))
    with pytest.raises(ValueError, match="invalid import transition"):
        repository.transition(
            batch.id, ImportBatchStatus.APPLIED, datetime(2026, 3, 1, 1, tzinfo=UTC)
        )
