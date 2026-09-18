from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from openpyxl import Workbook

from adams_tutoria.evolution_xlsx import import_evolution_xlsx, parse_evolution_xlsx
from adams_tutoria.persistence.database import connection, initialize_database


def _xlsx(path: Path, g: str = "8.00%", include_second: bool = True) -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(["Usuario", "Apellidos", "Nombre", "Provincia", "Grupo", "Entradas", "Evolución"])
    sheet.append(["SYN-001", "Synthetic", "Student", "Nowhere", "G", 1, g])
    sheet.append(["Evolución por bloques de primer y segundo nivel"])
    sheet.append(["Nombre", "Porcentaje evolución"])
    sheet.append(["Presentación", "100.00%"])
    sheet.append(["Módulo 1", "25.00%"])
    sheet.append(["1. Introducción sintética I", "100.00%"])
    sheet.append(["Actividad sintética", "99.00%"])
    if include_second:
        sheet.append(["Módulo 2", "0.00%"])
    book.save(path)


def _identity(path: Path, edition_id: str, enrollment_id: str) -> None:
    with connection(path) as db:
        db.execute(
            "INSERT INTO course VALUES(?,?,?,NULL,NULL,NULL,NULL,NULL)", ("c", "Synthetic", "S")
        )
        db.execute(
            "INSERT INTO edition VALUES(?,?,?,?,?,?)",
            (edition_id, "c", "Edition", None, None, None),
        )
        db.execute(
            "INSERT INTO student VALUES(?,?,?,?)", ("s", "Synthetic Student", None, "SYN-001")
        )
        db.execute("INSERT INTO enrollment VALUES(?,?,?,?)", (enrollment_id, "s", edition_id, None))
        db.execute(
            "INSERT INTO enrollment_external_identity VALUES(?,?,?,?,?)",
            ("dni", "global", "SYN-001", edition_id, enrollment_id),
        )


def test_parse_filters_content_and_separates_global_g(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.xlsx"
    _xlsx(source)
    blocks, diagnostics = parse_evolution_xlsx(source)
    assert sum(item.code == "excluded" for item in diagnostics) == 2
    assert blocks[0].user == "SYN-001"
    assert blocks[0].global_g_percentage == 8
    assert [row.title for row in blocks[0].rows] == [
        "Módulo 1",
        "1. Introducción sintética I",
        "Módulo 2",
    ]


def test_confirmed_import_is_idempotent_and_preserves_absence(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite3"
    initialize_database(database)
    edition, enrollment = str(uuid4()), str(uuid4())
    _identity(database, edition, enrollment)
    first = tmp_path / "first.xlsx"
    _xlsx(first)
    when = datetime(2026, 9, 18, tzinfo=UTC)
    preview = import_evolution_xlsx(first, database, UUID(edition), when)
    assert not preview.applied
    applied = import_evolution_xlsx(first, database, UUID(edition), when, confirm=True)
    assert applied.applied and applied.inserted_or_updated == 4
    second = tmp_path / "second.xlsx"
    _xlsx(second, "9.00%", include_second=False)
    repeat = import_evolution_xlsx(
        second, database, UUID(edition), when.replace(day=19), confirm=True
    )
    assert repeat.applied and repeat.inserted_or_updated == 1
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM content_progress_current").fetchone()[0] == 3
        assert (
            db.execute("SELECT global_g_percentage FROM enrollment_progress_current").fetchone()[0]
            == "9.00"
        )


def test_preview_reports_real_counters_and_rejects_unresolved_blocks(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite3"
    initialize_database(database)
    edition, enrollment = str(uuid4()), str(uuid4())
    _identity(database, edition, enrollment)
    source = tmp_path / "synthetic.xlsx"
    _xlsx(source)
    book = Workbook()
    sheet = book.active
    sheet.append(["Usuario", "Apellidos", "Nombre", "Provincia", "Grupo", "Entradas", "Evolución"])
    sheet.append(["SYN-404", "Synthetic", "Missing", "Nowhere", "G", 1, "4.00%"])
    sheet.append(["Evolución por bloques de primer y segundo nivel"])
    sheet.append(["Nombre", "Porcentaje evolución"])
    sheet.append(["Módulo 1", "0.00%"])
    book.save(source)

    result = import_evolution_xlsx(
        source, database, UUID(edition), datetime(2026, 9, 18, tzinfo=UTC)
    )
    assert result.preview is not None
    assert result.preview.changed == 0
    assert result.preview.unchanged == 0
    assert result.preview.rejected == 1
    assert result.preview.excluded == 0
    assert {diagnostic.code for diagnostic in result.diagnostics} == {"enrollment_not_found"}


def test_submodule_never_creates_an_implicit_parent(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite3"
    initialize_database(database)
    edition, enrollment = str(uuid4()), str(uuid4())
    _identity(database, edition, enrollment)
    book = Workbook()
    sheet = book.active
    sheet.append(["Usuario", "Apellidos", "Nombre", "Provincia", "Grupo", "Entradas", "Evolución"])
    sheet.append(["SYN-001", "Synthetic", "Student", "Nowhere", "G", 1, "8.00%"])
    sheet.append(["Evolución por bloques de primer y segundo nivel"])
    sheet.append(["Nombre", "Porcentaje evolución"])
    sheet.append(["1. Sólo submódulo I", "25.00%"])
    source = tmp_path / "submodule-only.xlsx"
    book.save(source)

    result = import_evolution_xlsx(
        source, database, UUID(edition), datetime(2026, 9, 18, tzinfo=UTC), confirm=True
    )
    assert result.rejected == 1
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM content_node").fetchone()[0] == 0


def test_boundaries_zero_and_hundred_are_accepted(tmp_path: Path) -> None:
    source = tmp_path / "boundaries.xlsx"
    _xlsx(source, g="100%")
    book = Workbook()
    sheet = book.active
    sheet.append(["Usuario", "Apellidos", "Nombre", "Provincia", "Grupo", "Entradas", "Evolución"])
    sheet.append(["SYN-001", "Synthetic", "Student", "Nowhere", "G", 1, "0%"])
    sheet.append(["Evolución por bloques de primer y segundo nivel"])
    sheet.append(["Nombre", "Porcentaje evolución"])
    sheet.append(["Módulo 1", "0%"])
    book.save(source)
    blocks, diagnostics = parse_evolution_xlsx(source)
    assert not diagnostics
    assert blocks[0].global_g_percentage == 0
    assert blocks[0].rows[0].pages_percentage == 0


def test_invalid_percentages_are_diagnosed_without_preview_changes(tmp_path: Path) -> None:
    source = tmp_path / "invalid.xlsx"
    _xlsx(source, g="101%")
    blocks, diagnostics = parse_evolution_xlsx(source)
    assert not blocks
    assert {item.code for item in diagnostics} == {
        "excluded",
        "invalid_global_progress",
        "no_blocks",
    }


def test_module_and_submodule_in_one_batch_have_consistent_preview_and_apply(
    tmp_path: Path,
) -> None:
    database = tmp_path / "synthetic.sqlite3"
    initialize_database(database)
    edition, enrollment = str(uuid4()), str(uuid4())
    _identity(database, edition, enrollment)
    source = tmp_path / "parent-and-child.xlsx"
    _xlsx(source)
    when = datetime(2026, 9, 18, tzinfo=UTC)

    preview = import_evolution_xlsx(source, database, UUID(edition), when)
    assert preview.preview is not None
    assert not any(item.code == "parent_not_found" for item in preview.diagnostics)
    applied = import_evolution_xlsx(source, database, UUID(edition), when, confirm=True)

    assert applied.inserted_or_updated == preview.preview.changed
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM content_node").fetchone()[0] == 3


def test_apply_keeps_diagnostics_private_and_records_global_changes(tmp_path: Path) -> None:
    database = tmp_path / "synthetic.sqlite3"
    initialize_database(database)
    edition, enrollment = str(uuid4()), str(uuid4())
    _identity(database, edition, enrollment)
    source = tmp_path / "synthetic.xlsx"
    _xlsx(source, g="8%")
    result = import_evolution_xlsx(
        source, database, UUID(edition), datetime(2026, 9, 18, tzinfo=UTC), confirm=True
    )
    assert result.inserted_or_updated == 4
    assert result.excluded == 2
    with connection(database) as db:
        batch = db.execute(
            "SELECT accepted_count, finished_at, scope_type, scope_reference, idempotency_key "
            "FROM import_batch"
        ).fetchone()
        assert batch[0] == 4
        assert batch[1] == "2026-09-18T00:00:00+00:00"
        assert batch[2:] == ("partial", edition, batch[4])
        changes = db.execute(
            "SELECT entity_type, change_type, diagnostic_message FROM import_batch_change "
            "ORDER BY id"
        ).fetchall()
        assert any(row[0] == "global_progress" and row[1] == "CHANGE" for row in changes)
        assert all("SYN-001" not in (row[2] or "") for row in changes)


def test_apply_rolls_back_everything_when_persistence_fails_mid_operation(
    tmp_path: Path,
) -> None:
    """A failure after planning must not leave partial state or audit rows."""
    database = tmp_path / "synthetic.sqlite3"
    initialize_database(database)
    edition, enrollment = str(uuid4()), str(uuid4())
    _identity(database, edition, enrollment)
    source = tmp_path / "synthetic.xlsx"
    _xlsx(source)
    with connection(database) as db:
        db.execute(
            "CREATE TRIGGER fail_evolution_apply "
            "AFTER INSERT ON content_progress_current "
            "BEGIN SELECT RAISE(ABORT, 'synthetic apply failure'); END"
        )

    with pytest.raises(Exception, match="synthetic apply failure"):
        import_evolution_xlsx(
            source, database, UUID(edition), datetime(2026, 9, 18, tzinfo=UTC), confirm=True
        )

    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM import_batch_change").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM content_node").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM content_progress_current").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM enrollment_progress_current").fetchone()[0] == 0
