from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.domain import ImportBatch, ImportBatchStatus, ImportSourceType
from adams_tutoria.excel_contract import StudentExcelAdapter, StudentExcelColumns
from adams_tutoria.persistence.database import connection, initialize_database
from adams_tutoria.student_reconciliation import StudentReconciliationService


def _batch(edition_id, *, key: str, scope: str = "partial") -> ImportBatch:
    return ImportBatch(
        uuid4(),
        ImportSourceType.EXCEL,
        "synthetic-students.xlsx",
        datetime(2026, 1, 1, tzinfo=UTC),
        ImportBatchStatus.CONFIRMED,
        source_reference="local://synthetic",
        source_fingerprint="b" * 64,
        total_count=1,
        accepted_count=1,
        scope_type=scope,
        scope_reference=str(edition_id),
        idempotency_key=key,
    )


@pytest.fixture
def database(tmp_path: Path):
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "Edición sintética"),
        )
    return path, edition_id


def _records():
    return (
        StudentExcelAdapter(
            StudentExcelColumns("name", "email", "source", "context", "sid", "action", "group"),
            source_name="synthetic.xlsx",
        )
        .adapt(
            [
                {
                    "name": "Alumno 001",
                    "email": "a001@example.invalid",
                    "source": "s",
                    "context": "e",
                    "sid": "1",
                    "action": None,
                    "group": None,
                }
            ]
        )
        .accepted
    )


def test_excel_students_create_idempotent_enrollment(database) -> None:
    path, edition_id = database
    service = StudentReconciliationService(path)
    first = service.apply_records(
        _batch(edition_id, key="batch-1"), _records(), edition_id, datetime(2026, 1, 2, tzinfo=UTC)
    )
    second = service.apply_records(
        _batch(edition_id, key="batch-2"), _records(), edition_id, datetime(2026, 1, 3, tzinfo=UTC)
    )
    assert first.created == 1
    assert second.unchanged == 1
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 1


def test_missing_edition_is_rejected_without_creation(database) -> None:
    path, edition_id = database
    with pytest.raises(ValueError, match="existing edition"):
        StudentReconciliationService(path).apply_records(
            _batch(uuid4(), key="missing"), _records(), edition_id, datetime(2026, 1, 2, tzinfo=UTC)
        )
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM edition").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 0


def test_full_scope_absence_and_explicit_reactivation(database) -> None:
    path, edition_id = database
    service = StudentReconciliationService(path)
    service.apply_records(
        _batch(edition_id, key="full-1", scope="full"),
        _records(),
        edition_id,
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    absent = service.apply_records(
        _batch(edition_id, key="full-2", scope="full"),
        (),
        edition_id,
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert absent.deactivated == 1
