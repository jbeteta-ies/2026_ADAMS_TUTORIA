from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from adams_tutoria.domain import ImportBatch, ImportBatchStatus, ImportSourceType
from adams_tutoria.enrollment_lifecycle import EnrollmentLifecycleService
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
from adams_tutoria.persistence.database import connection, initialize_database


def _candidate(
    student_id: str,
    edition_id: UUID,
    *,
    name: str | None = "Alumno Sintético",
    email: str | None = "alumno@example.invalid",
    action: str | None = None,
    enrollment_id: str | None = None,
    enrollment_external_id: str | None = None,
) -> ImportCandidate:
    return ImportCandidate(
        entity=ImportEntity.ENROLLMENT,
        provenance=Provenance("synthetic.xlsx", "test", 1, student_id),
        enrollment=EnrollmentEvidence(
            enrollment_reference=ResolutionReference(enrollment_id or student_id),
            student=StudentEvidence(
                name=name,
                email=email,
                external_identity=ExternalStudentIdentity("synthetic", "edition", student_id),
            ),
            edition=EditionEvidence(ResolutionReference(edition_id)),
        ),
        values=(
            (("enrollment_external_id", enrollment_external_id),)
            if enrollment_external_id is not None
            else ()
        ),
        action=action,
    )


def _batch(
    *,
    batch_id: UUID | None = None,
    edition_id: UUID | None = None,
    key: str | None = None,
    scope: str = "partial",
    status: ImportBatchStatus = ImportBatchStatus.CONFIRMED,
) -> ImportBatch:
    return ImportBatch(
        id=batch_id or uuid4(),
        source_type=ImportSourceType.EXCEL,
        source_name="synthetic.xlsx",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        status=status,
        source_reference="local://synthetic.xlsx",
        source_fingerprint="a" * 64,
        total_count=1,
        accepted_count=1,
        scope_type=scope,
        scope_reference=str(edition_id) if edition_id else None,
        idempotency_key=key,
    )


@pytest.fixture
def lifecycle_db(tmp_path: Path) -> tuple[Path, UUID]:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    edition_id = uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(uuid4()), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), db.execute("SELECT id FROM course").fetchone()[0], "Edición 1"),
        )
    return path, edition_id


def test_lifecycle_creates_modifies_completes_and_is_idempotent(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    first = _batch(edition_id=edition_id, key="batch-1")
    candidate = _candidate("stu-1", edition_id, email=None)
    assert service.apply(first, [candidate], datetime(2026, 1, 2, tzinfo=UTC)).created == 1

    second = _batch(edition_id=edition_id, key="batch-2")
    result = service.apply(
        second,
        [_candidate("stu-1", edition_id, name=None, email="alumno@example.invalid")],
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert result.conflicts == 1
    assert service.apply(first, [candidate], datetime(2026, 1, 4, tzinfo=UTC)).processed == 0
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT COUNT(*) FROM student_history WHERE event_type='modified'"
            ).fetchone()[0]
            == 0
        )


def test_full_scope_absence_and_reactivation_are_logical(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    service.apply(
        _batch(edition_id=edition_id, key="full-1", scope="full"),
        [_candidate("stu-1", edition_id)],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    result = service.apply(
        _batch(edition_id=edition_id, key="full-2", scope="full"),
        [],
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert result.absent == result.deactivated == 1
    result = service.apply(
        _batch(edition_id=edition_id, key="partial-3"),
        [_candidate("stu-1", edition_id, action="reactivate")],
        datetime(2026, 1, 4, tzinfo=UTC),
    )
    assert result.reactivated == 1
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 1


@pytest.mark.parametrize("status", [ImportBatchStatus.REJECTED, ImportBatchStatus.FAILED])
def test_lifecycle_rejects_batches_that_are_not_confirmed(lifecycle_db, status) -> None:
    path, edition_id = lifecycle_db
    with pytest.raises(ValueError, match="pending or confirmed"):
        EnrollmentLifecycleService(path).apply(
            _batch(edition_id=edition_id, key=f"invalid-{status.value}", status=status),
            [_candidate("stu-invalid", edition_id)],
            datetime(2026, 1, 2, tzinfo=UTC),
        )
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0


@pytest.mark.parametrize("terminal_status", ["applied", "rejected", "failed"])
def test_persisted_terminal_batches_are_not_reapplied(lifecycle_db, terminal_status) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    batch = _batch(edition_id=edition_id, key=f"persisted-{terminal_status}")

    # Persist the batch first, then simulate a terminal outcome recorded by an
    # earlier execution. The in-memory object remains applicable-shaped so the
    # persisted status is what this regression test exercises.
    service.apply(batch, [], datetime(2026, 1, 2, tzinfo=UTC))
    with connection(path) as db:
        db.execute(
            "UPDATE import_batch SET status=? WHERE id=?",
            (terminal_status, str(batch.id)),
        )

    result = service.apply(
        batch,
        [_candidate(f"terminal-{terminal_status}", edition_id)],
        datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert result.processed == 0
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM import_batch_change").fetchone()[0] == 0
        assert db.execute("SELECT status FROM import_batch").fetchone()[0] == terminal_status


@pytest.mark.parametrize("initial_student", [False, True])
def test_enrollment_key_collision_never_reassigns_or_writes_wrong_student(
    lifecycle_db, initial_student: bool
) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    service.apply(
        _batch(edition_id=edition_id, key="collision-owner"),
        [_candidate("stu-owner", edition_id, enrollment_id="shared-enrollment")],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    if initial_student:
        service.apply(
            _batch(edition_id=edition_id, key="collision-candidate"),
            [
                ImportCandidate(
                    entity=ImportEntity.STUDENT,
                    provenance=Provenance("synthetic.xlsx", "test", 2, "stu-candidate"),
                    student=StudentEvidence(
                        name="Alumno Candidato",
                        external_identity=ExternalStudentIdentity(
                            "synthetic", "edition", "stu-candidate"
                        ),
                    ),
                )
            ],
            datetime(2026, 1, 2, tzinfo=UTC),
        )

    result = service.apply(
        _batch(edition_id=edition_id, key=f"collision-{initial_student}"),
        [
            _candidate(
                "stu-candidate",
                edition_id,
                name="Alumno Candidato",
                enrollment_id="shared-enrollment",
                email=None if initial_student else "alumno@example.invalid",
            )
        ],
        datetime(2026, 1, 3, tzinfo=UTC),
    )

    assert result.conflicts == 1
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 1
        owner = db.execute("SELECT student_id FROM enrollment").fetchone()[0]
        assert db.execute(
            "SELECT COUNT(*) FROM student_external_identity WHERE source_student_id='stu-candidate'"
        ).fetchone()[0] == int(initial_student)
        assert (
            db.execute(
                "SELECT COUNT(*) FROM import_batch_change WHERE diagnostic_code=?",
                ("enrollment_student_mismatch",),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT student_id FROM enrollment "
                "WHERE id=(SELECT enrollment_id FROM enrollment_external_identity)"
            ).fetchone()[0]
            == owner
        )


def test_conflict_scope_and_idempotency_key_are_safe(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    batch = _batch(edition_id=edition_id, key="same-key")
    service.apply(batch, [_candidate("stu-1", edition_id)], datetime(2026, 1, 2, tzinfo=UTC))
    with pytest.raises(ValueError, match="another batch"):
        service.apply(
            _batch(edition_id=edition_id, key="same-key"),
            [],
            datetime(2026, 1, 3, tzinfo=UTC),
        )


def test_conflict_in_full_batch_is_present_and_not_deactivated(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    service.apply(
        _batch(edition_id=edition_id, key="full-conflict-1", scope="full"),
        [_candidate("stu-1", edition_id)],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    result = service.apply(
        _batch(edition_id=edition_id, key="full-conflict-2", scope="full"),
        [_candidate("stu-1", edition_id, name="Nombre contradictorio")],
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert result.conflicts == 1
    assert result.absent == result.deactivated == 0
    with connection(path) as db:
        assert db.execute("SELECT active FROM enrollment_state").fetchone()[0] == 1
        change = db.execute(
            "SELECT diagnostic_code, diagnostic_message FROM import_batch_change "
            "WHERE change_type='conflict' ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        assert change[0] == "identity_attributes_conflict"
        assert change[1] != change[0]


def test_full_absence_has_explicit_audit_without_source_row(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    service.apply(
        _batch(edition_id=edition_id, key="full-audit-1", scope="full"),
        [_candidate("stu-1", edition_id)],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    service.apply(
        _batch(edition_id=edition_id, key="full-audit-2", scope="full"),
        [],
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    with connection(path) as db:
        change = db.execute(
            "SELECT change_type, source_row_number, diagnostic_code FROM import_batch_change "
            "WHERE change_type='absent'"
        ).fetchone()
        assert tuple(change) == ("absent", None, "absent_from_full_scope")


def test_full_scope_includes_legacy_enrollment_without_state_row(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    enrollment_id, student_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute(
            "INSERT INTO student(id,full_name) VALUES(?,?)", (str(student_id), "Legacy Student")
        )
        db.execute(
            "INSERT INTO enrollment(id,student_id,edition_id) VALUES(?,?,?)",
            (str(enrollment_id), str(student_id), str(edition_id)),
        )
        db.execute(
            "INSERT INTO enrollment_external_identity VALUES(?,?,?,?,?)",
            ("synthetic", "edition", "legacy-enrollment", str(edition_id), str(enrollment_id)),
        )
    result = EnrollmentLifecycleService(path).apply(
        _batch(edition_id=edition_id, key="legacy-full", scope="full"),
        [],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert result.absent == result.deactivated == 1
    with connection(path) as db:
        assert (
            db.execute(
                "SELECT active FROM enrollment_state WHERE enrollment_id=?", (str(enrollment_id),)
            ).fetchone()[0]
            == 0
        )


def test_existing_student_with_null_email_matches_resolver_contract(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    service.apply(
        _batch(edition_id=edition_id, key="null-email-1"),
        [_candidate("stu-null-email", edition_id, email=None)],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    result = service.apply(
        _batch(edition_id=edition_id, key="null-email-2"),
        [_candidate("stu-null-email", edition_id, email="new@example.invalid")],
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert result.conflicts == 1
    with connection(path) as db:
        assert db.execute("SELECT email FROM student").fetchone()[0] is None


def test_student_only_candidate_updates_identity_without_creating_enrollment(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    candidate = ImportCandidate(
        entity=ImportEntity.STUDENT,
        provenance=Provenance("synthetic.xlsx", "test", 2, "stu-only"),
        student=StudentEvidence(
            name="Alumno Solo",
            external_identity=ExternalStudentIdentity("synthetic", "edition", "stu-only"),
        ),
    )
    result = service.apply(
        _batch(edition_id=edition_id, key="student-only"),
        [candidate],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert result.created == 1
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 0


def test_partial_scope_rejects_unknown_scope_reference_without_writes(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    batch = _batch(edition_id=uuid4(), key="partial-invalid", scope="partial")
    with pytest.raises(ValueError, match="existing edition"):
        service.apply(batch, [], datetime(2026, 1, 2, tzinfo=UTC))
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0


def test_invalid_full_scope_rolls_back_candidate_and_batch(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    with pytest.raises(ValueError, match="existing edition"):
        service.apply(
            _batch(edition_id=uuid4(), key="rollback-full", scope="full"),
            [_candidate("stu-rollback", edition_id)],
            datetime(2026, 1, 2, tzinfo=UTC),
        )
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0


def test_reactivation_and_enrollment_attribute_conflicts_are_auditable(lifecycle_db) -> None:
    path, edition_id = lifecycle_db
    service = EnrollmentLifecycleService(path)
    service.apply(
        _batch(edition_id=edition_id, key="critical-1"),
        [_candidate("stu-critical", edition_id, enrollment_id="enr-critical")],
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    with connection(path) as db:
        db.execute("UPDATE enrollment SET external_id='stored-external' WHERE external_id IS NULL")
        enrollment_id = db.execute("SELECT id FROM enrollment").fetchone()[0]
        db.execute("UPDATE enrollment_state SET active=0 WHERE enrollment_id=?", (enrollment_id,))
    result = service.apply(
        _batch(edition_id=edition_id, key="critical-2"),
        [_candidate("stu-critical", edition_id, enrollment_id="enr-critical")],
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert result.conflicts == 1

    result = service.apply(
        _batch(edition_id=edition_id, key="critical-3"),
        [_candidate("stu-critical", edition_id, action="reactivate", enrollment_id="enr-critical")],
        datetime(2026, 1, 4, tzinfo=UTC),
    )
    assert result.reactivated == 1
    with connection(path) as db:
        assert db.execute("SELECT active FROM enrollment_state").fetchone()[0] == 1

    result = service.apply(
        _batch(edition_id=edition_id, key="critical-4"),
        [
            _candidate(
                "stu-critical",
                edition_id,
                enrollment_id="enr-critical",
                enrollment_external_id="different-external",
            )
        ],
        datetime(2026, 1, 5, tzinfo=UTC),
    )
    assert result.conflicts == 1


def test_lifecycle_schema_migrates_legacy_import_batch(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with connection(path) as db:
        db.execute(
            "CREATE TABLE import_batch (id TEXT PRIMARY KEY, source_type TEXT NOT NULL, "
            "source_name TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, "
            "status TEXT NOT NULL, source_reference TEXT, source_fingerprint TEXT, "
            "context TEXT, action TEXT, group_name TEXT, total_count INTEGER NOT NULL DEFAULT 0, "
            "accepted_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0, "
            "warning_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0)"
        )
    initialize_database(path)
    with connection(path) as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(import_batch)")}
        assert {"scope_type", "scope_reference", "idempotency_key"} <= columns
