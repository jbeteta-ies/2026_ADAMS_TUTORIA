"""Synthetic integration coverage for evaluation application."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from adams_tutoria.domain import Course, Edition, Enrollment, ImportBatch, ImportSourceType, Student
from adams_tutoria.evaluation_import import EvaluationImportService
from adams_tutoria.excel_contract import (
    EvaluationRecord,
    EvaluationResult,
    EvaluationResultStatus,
    EvaluationStatus,
)
from adams_tutoria.import_contract import ExternalStudentIdentity
from adams_tutoria.persistence.database import connection, initialize_database
from adams_tutoria.persistence.repositories import (
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    StudentRepository,
)


def _batch(*, key: str | None = None) -> ImportBatch:
    return ImportBatch(
        uuid4(),
        ImportSourceType.EXCEL,
        "synthetic-evaluations.xlsx",
        datetime(2026, 3, 1, 10, tzinfo=UTC),
        context="edition-x",
        idempotency_key=key,
    )


def _record(
    enrollment_id: str,
    *,
    reference: str = "evaluation-x",
    result: EvaluationResultStatus = EvaluationResultStatus.ATTEMPTED,
    score: str | None = "8",
) -> EvaluationRecord:
    from decimal import Decimal

    return EvaluationRecord(
        EvaluationStatus.COMPLETED,
        target=reference,
        evaluation_id=reference,
        score=Decimal(score) if score is not None else None,
        max_score=Decimal("10") if score is not None else None,
        enrollment_id=enrollment_id,
        identity=ExternalStudentIdentity("synthetic", "edition-x", "student-x"),
        result=EvaluationResult(result, score, Decimal(score) if score is not None else None),
    )


def _prepare(path: Path):
    initialize_database(path)
    course = Course(uuid4(), "Synthetic course", "SYN")
    edition = Edition(uuid4(), course, "Synthetic edition", "edition-x")
    student = Student(uuid4(), "Synthetic Student", "student@example.invalid", "student-x")
    enrollment = Enrollment(uuid4(), student, edition, "enrollment-x")
    CourseRepository(path).save(course)
    EditionRepository(path).save(edition)
    StudentRepository(path).save(student)
    EnrollmentRepository(path).save(enrollment)
    with connection(path) as db:
        db.execute(
            "INSERT INTO enrollment_external_identity "
            "(source,context,source_enrollment_id,edition_id,enrollment_id) VALUES(?,?,?,?,?)",
            ("synthetic", "edition-x", "enrollment-x", str(edition.id), str(enrollment.id)),
        )
    return course, edition, student, enrollment


def test_evaluation_import_resolves_existing_enrollment_without_content_node(
    tmp_path: Path,
) -> None:
    path = tmp_path / "evaluations.sqlite3"
    _, _, _, enrollment = _prepare(path)
    record = _record(str(enrollment.id))
    result = EvaluationImportService(path).apply(
        _batch(), (record,), datetime(2026, 3, 1, tzinfo=UTC)
    )

    assert (result.processed, result.inserted, result.rejected) == (1, 1, 0)
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM content_node").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM content_progress_snapshot").fetchone()[0] == 0


def test_evaluation_import_is_idempotent_and_changed_values_are_historical(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    _, _, _, enrollment = _prepare(path)
    service = EvaluationImportService(path)
    first = _batch()
    changed = _batch()
    assert (
        service.apply(
            first, (_record(str(enrollment.id)),), datetime(2026, 3, 1, tzinfo=UTC)
        ).inserted
        == 1
    )
    assert (
        service.apply(
            changed, (_record(str(enrollment.id)),), datetime(2026, 3, 2, tzinfo=UTC)
        ).unchanged
        == 1
    )
    assert (
        service.apply(
            _batch(), (_record(str(enrollment.id), score="9"),), datetime(2026, 3, 3, tzinfo=UTC)
        ).changed
        == 1
    )
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM evaluation_history").fetchone()[0] == 2


def test_evaluation_import_preserves_result_semantics_and_records_diagnostics(
    tmp_path: Path,
) -> None:
    path = tmp_path / "semantics.sqlite3"
    _, _, _, enrollment = _prepare(path)
    records = (
        _record(
            str(enrollment.id),
            reference="not-attempted",
            result=EvaluationResultStatus.NOT_ATTEMPTED,
            score=None,
        ),
        _record(str(enrollment.id), reference="attempted"),
        _record(
            str(enrollment.id),
            reference="unknown",
            result=EvaluationResultStatus.UNKNOWN,
            score=None,
        ),
        EvaluationRecord(EvaluationStatus.COMPLETED, enrollment_id=str(enrollment.id)),
        EvaluationRecord(
            EvaluationStatus.COMPLETED, target="unresolved", enrollment_id=str(uuid4())
        ),
    )
    result = EvaluationImportService(path).apply(
        _batch(), records, datetime(2026, 3, 1, tzinfo=UTC)
    )

    assert (result.inserted, result.rejected) == (3, 2)
    with connection(path) as db:
        statuses = {row[0] for row in db.execute("SELECT result_status FROM evaluation")}
        diagnostics = {
            row[0]
            for row in db.execute(
                "SELECT diagnostic_code FROM import_batch_change WHERE change_type='rejected'"
            )
        }
    assert statuses == {"not_attempted", "attempted", "unknown"}
    assert diagnostics == {"invalid_evaluation"}
