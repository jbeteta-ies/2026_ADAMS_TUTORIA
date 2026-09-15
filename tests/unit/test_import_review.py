from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.domain import ImportBatch, ImportBatchStatus, ImportSourceType
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
from adams_tutoria.import_review import (
    ConfirmationRequest,
    ImportReviewService,
    PreviewStaleError,
)
from adams_tutoria.persistence.database import connection, initialize_database


def test_preview_is_read_only_and_confirmation_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "Edición sintética"),
        )
    batch = ImportBatch(
        uuid4(),
        ImportSourceType.EXCEL,
        "synthetic.xlsx",
        datetime(2026, 1, 1, tzinfo=UTC),
        ImportBatchStatus.CONFIRMED,
        scope_reference=str(edition_id),
        idempotency_key="synthetic-batch",
    )
    candidate = ImportCandidate(
        ImportEntity.ENROLLMENT,
        Provenance("synthetic.xlsx", "excel", 2),
        enrollment=EnrollmentEvidence(
            ResolutionReference("enrollment-1"),
            StudentEvidence(
                name="Alumno 001",
                email="a001@example.invalid",
                external_identity=ExternalStudentIdentity("source", "edition", "student-1"),
            ),
            EditionEvidence(ResolutionReference(edition_id)),
        ),
    )
    service = ImportReviewService(path)
    preview = service.preview(
        batch, candidates=[candidate], created_at=datetime(2026, 1, 2, tzinfo=UTC)
    )
    assert preview.changes[0].change_type.value == "CHANGE"
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 0
    request = ConfirmationRequest(
        preview.preview_id, preview.digest, "all", datetime(2026, 1, 3, tzinfo=UTC), "confirm-1"
    )
    result = service.confirm(request)
    assert result.applied
    assert service.confirm(request).idempotent
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 1


def test_changed_database_invalidates_preview(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    batch = ImportBatch(
        uuid4(),
        ImportSourceType.EXCEL,
        "synthetic.xlsx",
        datetime(2026, 1, 1, tzinfo=UTC),
        ImportBatchStatus.CONFIRMED,
        idempotency_key="stale-batch",
    )
    service = ImportReviewService(path)
    preview = service.preview(batch, created_at=datetime(2026, 1, 2, tzinfo=UTC))
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(uuid4()), "Cambio sintético"))
    with pytest.raises(PreviewStaleError):
        service.confirm(
            ConfirmationRequest(
                preview.preview_id,
                preview.digest,
                "all",
                datetime(2026, 1, 3, tzinfo=UTC),
                "confirm-stale",
            )
        )


def test_confirmation_rolls_back_and_persists_failed_global_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    batch = ImportBatch(
        uuid4(), ImportSourceType.EXCEL, "synthetic.xlsx", datetime(2026, 1, 1, tzinfo=UTC)
    )
    service = ImportReviewService(path)
    preview = service.preview(batch, created_at=datetime(2026, 1, 2, tzinfo=UTC))

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic apply failure")

    monkeypatch.setattr(service, "_simulate", fail)
    result = service.confirm(
        ConfirmationRequest(
            preview.preview_id, preview.digest, "all", datetime(2026, 1, 3, tzinfo=UTC), "failed-1"
        )
    )

    assert not result.applied
    assert result.error == "synthetic apply failure"
    assert result.audit_error is None
    assert result.audit_persisted is True
    with connection(path) as db:
        batch_row = db.execute(
            "SELECT status FROM import_batch WHERE id=?", (str(batch.id),)
        ).fetchone()
        audit = db.execute(
            "SELECT entity_type, change_type, diagnostic_code, diagnostic_message "
            "FROM import_batch_change WHERE batch_id=?",
            (str(batch.id),),
        ).fetchone()
    assert batch_row["status"] == "failed"
    assert tuple(audit) == (
        "global",
        "error",
        "confirmation_failed",
        "Atomic confirmation failed; application changes were rolled back",
    )


def test_failed_second_transaction_is_not_reported_as_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    batch = ImportBatch(
        uuid4(), ImportSourceType.EXCEL, "synthetic.xlsx", datetime(2026, 1, 1, tzinfo=UTC)
    )
    service = ImportReviewService(path)
    preview = service.preview(batch, created_at=datetime(2026, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(
        service,
        "_simulate",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("original failure")),
    )
    monkeypatch.setattr(
        service, "_persist_failure", lambda *args, **kwargs: "audit transaction unavailable"
    )

    result = service.confirm(
        ConfirmationRequest(
            preview.preview_id, preview.digest, "all", datetime(2026, 1, 3, tzinfo=UTC), "failed-2"
        )
    )

    assert result.error == "original failure"
    assert result.audit_error == "audit transaction unavailable"
    assert result.audit_persisted is False
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0
