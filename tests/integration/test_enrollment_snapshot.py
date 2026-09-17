from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from adams_tutoria.domain import ImportBatch, ImportBatchStatus, ImportSourceType
from adams_tutoria.enrollment_lifecycle import EnrollmentLifecycleService
from adams_tutoria.enrollment_snapshot import EnrollmentSnapshotService
from adams_tutoria.excel_contract import EnrollmentSnapshotAdapter
from adams_tutoria.import_operation import ImportOperationService
from adams_tutoria.import_review import ImportChangeType
from adams_tutoria.import_ui import _count_name_changes, _count_operations
from adams_tutoria.persistence.database import connection, initialize_database


def test_snapshot_reconciles_absence_and_reactivation(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "Edición A"),
        )
    adapter = EnrollmentSnapshotAdapter()
    rows = adapter.adapt(
        [
            {"Usuario": "DNI-001", "Apellidos": "  García ", "Nombre": " Ana ", "Provincia": "X"},
            {"Usuario": "DNI-002", "Apellidos": "López", "Nombre": "Luis", "Grupo": "G"},
        ]
    )
    service = EnrollmentSnapshotService(path)

    def batch(key: str) -> ImportBatch:
        return ImportBatch(
            uuid4(),
            ImportSourceType.EXCEL,
            "local-snapshot",
            datetime(2026, 1, 1, tzinfo=UTC),
            ImportBatchStatus.CONFIRMED,
            total_count=2,
            accepted_count=2,
            scope_type="full",
            scope_reference=str(edition_id),
            idempotency_key=key,
        )

    assert (
        service.apply(
            batch("one"), rows.accepted, edition_id, datetime(2026, 1, 2, tzinfo=UTC)
        ).created
        == 2
    )
    assert (
        service.apply(
            batch("two"), rows.accepted[:1], edition_id, datetime(2026, 1, 3, tzinfo=UTC)
        ).deactivated
        == 1
    )
    changed = adapter.adapt(
        [{"Usuario": "DNI-002", "Apellidos": "López", "Nombre": "Luis"}]
    ).accepted
    assert (
        service.apply(
            batch("three"), changed, edition_id, datetime(2026, 1, 4, tzinfo=UTC)
        ).reactivated
        == 1
    )
    assert (
        service.apply(
            batch("four"), changed, edition_id, datetime(2026, 1, 5, tzinfo=UTC)
        ).unchanged
        == 1
    )
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 2


def test_snapshot_normalizes_name_and_preserves_student_id_on_rename(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "Edición A"),
        )
    adapter = EnrollmentSnapshotAdapter()
    service = EnrollmentSnapshotService(path)
    first = adapter.adapt(
        [{"Usuario": "DNI-003", "Apellidos": "  Dos  Apellidos ", "Nombre": "  Eva  "}]
    ).accepted
    service.apply(
        ImportBatch(
            uuid4(),
            ImportSourceType.EXCEL,
            "synthetic",
            datetime(2026, 1, 1, tzinfo=UTC),
            ImportBatchStatus.CONFIRMED,
            total_count=1,
            accepted_count=1,
            scope_type="full",
            scope_reference=str(edition_id),
            idempotency_key="name-1",
        ),
        first,
        edition_id,
        datetime(2026, 1, 2, tzinfo=UTC),
    )
    with connection(path) as db:
        student_id = db.execute("SELECT id FROM student").fetchone()[0]
        assert db.execute("SELECT full_name FROM student").fetchone()[0] == "Dos Apellidos Eva"
    renamed = adapter.adapt(
        [{"Usuario": "DNI-003", "Apellidos": "Dos Apellidos", "Nombre": "Iris"}]
    ).accepted
    result = service.apply(
        ImportBatch(
            uuid4(),
            ImportSourceType.EXCEL,
            "synthetic",
            datetime(2026, 1, 3, tzinfo=UTC),
            ImportBatchStatus.CONFIRMED,
            total_count=1,
            accepted_count=1,
            scope_type="full",
            scope_reference=str(edition_id),
            idempotency_key="name-2",
        ),
        renamed,
        edition_id,
        datetime(2026, 1, 4, tzinfo=UTC),
    )
    assert result.modified == 1
    with connection(path) as db:
        assert db.execute("SELECT id FROM student").fetchone()[0] == student_id
        assert db.execute("SELECT full_name FROM student").fetchone()[0] == "Dos Apellidos Iris"
        assert (
            db.execute(
                "SELECT COUNT(*) FROM student_history WHERE event_type='modified'"
            ).fetchone()[0]
            == 1
        )


def test_prepare_snapshot_accepts_uploaded_file_and_forces_full_scope(
    tmp_path: Path,
) -> None:
    from openpyxl import Workbook

    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "Edición A"),
        )
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Usuario", "Apellidos", "Nombre", "Columna ignorada"])
    sheet.append(["DNI-004", "Alumno", "Sintético", "no persistir"])
    stream = BytesIO()
    workbook.save(stream)
    prepared = ImportOperationService(path).prepare_snapshot_xlsx(
        stream, edition_id=str(edition_id), created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert prepared.batch.scope_type == "full"
    assert prepared.batch.scope_reference == str(edition_id)
    assert not prepared.blocked


def test_snapshot_scope_isolated_between_editions(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_a, edition_b = uuid4(), uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        for edition_id, label in ((edition_a, "A"), (edition_b, "B")):
            db.execute(
                "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
                (str(edition_id), str(course_id), label),
            )
    adapter = EnrollmentSnapshotAdapter()
    service = EnrollmentSnapshotService(path)
    records = adapter.adapt(
        [{"Usuario": "DNI-010", "Apellidos": "Alumno", "Nombre": "Uno"}]
    ).accepted

    def make_batch(key: str, edition_id) -> ImportBatch:
        return ImportBatch(
            uuid4(),
            ImportSourceType.EXCEL,
            "synthetic",
            datetime(2026, 1, 1, tzinfo=UTC),
            ImportBatchStatus.CONFIRMED,
            total_count=1,
            accepted_count=1,
            scope_type="full",
            scope_reference=str(edition_id),
            idempotency_key=key,
        )

    service.apply(
        make_batch("edition-a", edition_a), records, edition_a, datetime(2026, 1, 2, tzinfo=UTC)
    )
    service.apply(
        make_batch("edition-b", edition_b), records, edition_b, datetime(2026, 1, 3, tzinfo=UTC)
    )
    empty = service.apply(
        make_batch("edition-a-empty", edition_a), (), edition_a, datetime(2026, 1, 4, tzinfo=UTC)
    )

    assert empty.deactivated == 1
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM enrollment_state WHERE active=1").fetchone()[0] == 1


def test_repeating_same_snapshot_four_new_preparations_is_idempotent(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "A"),
        )
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Usuario", "Apellidos", "Nombre"])
    sheet.append(["DNI-011", "Alumno", "Dos"])
    stream = BytesIO()
    workbook.save(stream)
    service = ImportOperationService(path)
    key = None
    results = []
    for index in range(4):
        prepared = service.prepare_snapshot_xlsx(
            BytesIO(stream.getvalue()),
            edition_id=str(edition_id),
            created_at=datetime(2026, 2, index + 1, tzinfo=UTC),
        )
        key = key or f"snapshot-{prepared.batch.source_fingerprint}-{edition_id}"
        results.append(
            service.confirm(
                prepared,
                operator_reference="synthetic",
                timestamp=datetime(2026, 2, index + 5, tzinfo=UTC),
                idempotency_key=key,
            )
        )

    assert results[0].applied
    assert all(result.idempotent for result in results[1:])
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM student_history").fetchone()[0] == 1


def test_snapshot_preview_reports_all_lifecycle_categories(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "A"),
        )
    adapter = EnrollmentSnapshotAdapter()
    lifecycle = EnrollmentSnapshotService(path)

    def records(*items: tuple[str, str, str]):
        return adapter.adapt(
            [{"Usuario": dni, "Apellidos": surname, "Nombre": name} for dni, surname, name in items]
        ).accepted

    def batch(key: str) -> ImportBatch:
        return ImportBatch(
            uuid4(),
            ImportSourceType.EXCEL,
            "synthetic",
            datetime(2026, 3, 1, tzinfo=UTC),
            ImportBatchStatus.CONFIRMED,
            scope_type="full",
            scope_reference=str(edition_id),
            idempotency_key=key,
        )

    lifecycle.apply(
        batch("seed"),
        records(
            ("DNI-020", "Alumno", "Renombrado"),
            ("DNI-021", "Alumno", "Ausente"),
            ("DNI-022", "Alumno", "Reactiva"),
            ("DNI-023", "Alumno", "Igual"),
        ),
        edition_id,
        datetime(2026, 3, 2, tzinfo=UTC),
    )
    lifecycle.apply(
        batch("deactivate"),
        records(
            ("DNI-020", "Alumno", "Renombrado"),
            ("DNI-021", "Alumno", "Ausente"),
            ("DNI-023", "Alumno", "Igual"),
        ),
        edition_id,
        datetime(2026, 3, 3, tzinfo=UTC),
    )
    preview = ImportOperationService(path).review.preview(
        batch("preview"),
        candidates=EnrollmentSnapshotService(path).candidates(
            records(
                ("DNI-020", "Alumno", "Nuevo Nombre"),
                ("DNI-022", "Alumno", "Reactiva"),
                ("DNI-023", "Alumno", "Igual"),
                ("DNI-024", "Alumno", "Nueva Alta"),
            ),
            edition_id,
        ),
        created_at=datetime(2026, 3, 4, tzinfo=UTC),
    )

    assert _count_name_changes(preview) == 1
    assert _count_operations(preview, "created") == 1
    assert _count_operations(preview, "absent") == 1
    assert _count_operations(preview, "reactivated") == 1
    assert _count_operations(preview, "unchanged") == 1
    assert sum(change.change_type is ImportChangeType.CHANGE for change in preview.changes) == 4


def test_snapshot_confirmation_rolls_back_partial_lifecycle_failure(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "synthetic.sqlite3"
    initialize_database(path)
    course_id, edition_id = uuid4(), uuid4()
    with connection(path) as db:
        db.execute("INSERT INTO course(id,name) VALUES(?,?)", (str(course_id), "Curso sintético"))
        db.execute(
            "INSERT INTO edition(id,course_id,label) VALUES(?,?,?)",
            (str(edition_id), str(course_id), "A"),
        )
    adapter = EnrollmentSnapshotAdapter()
    records = adapter.adapt(
        [{"Usuario": "DNI-030", "Apellidos": "Alumno", "Nombre": "Atómico"}]
    ).accepted
    operation = ImportOperationService(path)
    prepared = operation.preview(
        "local-snapshot",
        candidates=EnrollmentSnapshotService(path).candidates(records, edition_id),
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
        scope_type="full",
        scope_reference=str(edition_id),
    )
    original = EnrollmentLifecycleService.apply_in_connection

    def fail_after_write(self, db, batch, candidates, occurred_at):
        original(self, db, batch, candidates, occurred_at)
        raise RuntimeError("synthetic snapshot failure")

    monkeypatch.setattr(EnrollmentLifecycleService, "apply_in_connection", fail_after_write)
    result = operation.confirm(
        prepared,
        operator_reference="synthetic",
        timestamp=datetime(2026, 4, 2, tzinfo=UTC),
        idempotency_key="snapshot-atomic",
    )

    assert not result.applied
    assert result.error == "synthetic snapshot failure"
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM enrollment").fetchone()[0] == 0
