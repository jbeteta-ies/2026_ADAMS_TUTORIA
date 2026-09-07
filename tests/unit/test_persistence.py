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
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationStatus,
    EvaluationTargetType,
    ProgressSnapshot,
    Student,
)
from adams_tutoria.persistence.database import connection, database_path, initialize_database
from adams_tutoria.persistence.repositories import (
    CommunicationRecordRepository,
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    EvaluationRepository,
    ProgressSnapshotRepository,
    StudentRepository,
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
            "evaluation",
            "communication_record",
        }
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connection_rolls_back_and_closes_transaction(tmp_path: Path) -> None:
    path = tmp_path / "transaction.sqlite3"
    initialize_database(path)
    with pytest.raises(RuntimeError), connection(path) as db:
        db.execute("INSERT INTO course VALUES(?,?,?,?)", ("rollback", "x", None, None))
        raise RuntimeError("synthetic failure")
    with connection(path) as db:
        assert db.execute("SELECT * FROM course").fetchone() is None


def test_all_entities_round_trip_every_field_and_relationship(tmp_path: Path) -> None:
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
