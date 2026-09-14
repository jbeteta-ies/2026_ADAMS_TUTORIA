"""Synthetic tests for idempotent evolution import."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from adams_tutoria.domain import (
    ContentNode,
    ContentNodeType,
    Edition,
    ImportBatch,
    ImportSourceType,
)
from adams_tutoria.excel_contract import ProgressRecord
from adams_tutoria.persistence.database import initialize_database
from adams_tutoria.persistence.repositories import (
    ContentNodeRepository,
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    StudentRepository,
)
from adams_tutoria.progress_import import ProgressImportService


def _graph():
    from adams_tutoria.domain import Course, Enrollment, Student

    course = Course(uuid4(), "Synthetic course", "SYN")
    edition = Edition(uuid4(), course, "Synthetic edition")
    student = Student(uuid4(), "Synthetic Student", "student@example.invalid")
    enrollment = Enrollment(uuid4(), student, edition, "enrollment-x")
    return course, edition, student, enrollment


def _ready(path: Path):
    initialize_database(path)
    course, edition, student, enrollment = _graph()
    CourseRepository(path).save(course)
    EditionRepository(path).save(edition)
    StudentRepository(path).save(student)
    EnrollmentRepository(path).save(enrollment)
    node = ContentNode(uuid4(), course, edition, ContentNodeType.MODULE, "Synthetic module")
    ContentNodeRepository(path).save(node)
    return edition, enrollment, node


def test_reimport_is_idempotent_but_value_change_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "progress.sqlite3"
    _, enrollment, node = _ready(path)
    captured = datetime(2026, 2, 1, tzinfo=UTC)
    record = ProgressRecord(
        Decimal("20"), enrollment_id=str(enrollment.id), node_id=str(node.id), recorded_at=captured
    )
    batch = ImportBatch(
        uuid4(), ImportSourceType.EXCEL, "synthetic", captured, total_count=1, accepted_count=1
    )
    service = ProgressImportService(path)
    assert service.apply(batch, (record,), captured).inserted == 1
    replay = ImportBatch(
        uuid4(),
        ImportSourceType.EXCEL,
        "synthetic",
        captured,
        total_count=1,
        accepted_count=1,
        idempotency_key="replay",
    )
    assert service.apply(replay, (record,), captured).unchanged == 1
    changed = ProgressRecord(
        Decimal("30"), enrollment_id=str(enrollment.id), node_id=str(node.id), recorded_at=captured
    )
    next_batch = ImportBatch(
        uuid4(), ImportSourceType.EXCEL, "synthetic", captured, total_count=1, accepted_count=1
    )
    assert service.apply(next_batch, (changed,), captured).inserted == 1


def test_invalid_progress_and_unknown_node_are_diagnosed(tmp_path: Path) -> None:
    path = tmp_path / "progress-invalid.sqlite3"
    _, enrollment, _ = _ready(path)
    now = datetime(2026, 2, 1, tzinfo=UTC)
    records = (
        ProgressRecord(
            Decimal("101"), enrollment_id=str(enrollment.id), node_id=str(uuid4()), recorded_at=now
        ),
    )
    batch = ImportBatch(
        uuid4(), ImportSourceType.EXCEL, "synthetic", now, total_count=1, accepted_count=1
    )
    result = ProgressImportService(path).apply(batch, records, now)
    assert result.rejected == 1
