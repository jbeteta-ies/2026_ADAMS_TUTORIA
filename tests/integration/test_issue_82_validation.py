"""Synthetic end-to-end regression coverage for Issue #82."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.domain import ImportBatch, ImportBatchStatus, ImportSourceType
from adams_tutoria.excel_contract import ProgressRecord
from adams_tutoria.import_contract import (
    EditionEvidence,
    EnrollmentEvidence,
    ExternalStudentIdentity,
    ImportCandidate,
    ImportEntity,
    Provenance,
    ResolutionReference,
    StudentEvidence,
)
from adams_tutoria.import_operation import ImportOperationService
from adams_tutoria.import_pipeline import InMemoryImportAdapter, dataset_from
from adams_tutoria.import_review import ConfirmationRequest, ImportReviewService
from adams_tutoria.persistence.database import connection, initialize_database


def _candidate(edition_id, student_id: str = "student-82") -> ImportCandidate:
    return ImportCandidate(
        ImportEntity.ENROLLMENT,
        Provenance("synthetic-memory", "memory", 1),
        enrollment=EnrollmentEvidence(
            ResolutionReference(student_id),
            StudentEvidence(
                name="Alumno 082",
                email="alumno082@example.invalid",
                external_identity=ExternalStudentIdentity("synthetic", "edition-82", student_id),
            ),
            EditionEvidence(ResolutionReference(edition_id)),
        ),
    )


def _edition(path: Path):
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute(
            "INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético 82")
        )
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "Edición sintética 82"),
        )
    return edition_id


def test_generic_adapter_is_idempotent_and_preserves_history(tmp_path: Path) -> None:
    path = tmp_path / "issue-82-synthetic.sqlite3"
    initialize_database(path)
    edition_id = _edition(path)
    candidate = _candidate(edition_id)
    service = ImportOperationService(path)
    prepared = service.prepare(
        InMemoryImportAdapter(dataset_from(candidates=(candidate,))),
        "synthetic-memory",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    first = service.confirm(
        prepared,
        operator_reference="test-operator",
        timestamp=datetime(2026, 8, 2, tzinfo=UTC),
        idempotency_key="issue-82-first",
    )
    repeated = service.confirm(
        prepared,
        operator_reference="test-operator",
        timestamp=datetime(2026, 8, 3, tzinfo=UTC),
        idempotency_key="issue-82-first",
    )

    assert first.applied and not first.idempotent
    assert repeated.idempotent and not repeated.applied
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM student_history").fetchone()[0] >= 1


def test_confirmation_rolls_back_all_entities_after_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "issue-82-rollback.sqlite3"
    initialize_database(path)
    edition_id = _edition(path)
    service = ImportReviewService(path)
    candidate = _candidate(edition_id, "rollback-student")
    batch = ImportBatch(
        uuid4(),
        ImportSourceType.OTHER,
        "local-source",
        datetime(2026, 8, 1, tzinfo=UTC),
        ImportBatchStatus.CONFIRMED,
    )

    def fail_after_enrollment(*args, **kwargs):
        raise RuntimeError("synthetic progress failure")

    preview = service.preview(
        batch,
        candidates=(candidate,),
        progress=(ProgressRecord(Decimal("50")),),
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    monkeypatch.setattr(
        "adams_tutoria.import_review.ProgressImportService.apply_in_connection",
        fail_after_enrollment,
    )
    result = service.confirm(
        ConfirmationRequest(
            preview.preview_id,
            preview.digest,
            "all",
            datetime(2026, 8, 2, tzinfo=UTC),
            "issue-82-rollback",
        )
    )

    assert result.error == "synthetic progress failure"
    assert result.audit_persisted
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT diagnostic_code FROM import_batch_change "
                "WHERE diagnostic_code='confirmation_failed'"
            ).fetchone()[0]
            == "confirmation_failed"
        )
