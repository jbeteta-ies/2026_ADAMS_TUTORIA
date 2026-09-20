"""Synthetic acceptance coverage for the strict positional evaluations workbook."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from openpyxl import Workbook

from adams_tutoria.evaluations_xlsx import import_evaluations_xlsx, parse_evaluations_xlsx
from adams_tutoria.persistence.database import connection, initialize_database


def _workbook(path: Path, values: tuple[object, ...] = ("0", "50 (50)", "60 (60)", "")) -> None:
    book = Workbook()
    sheet = book.active
    for block, user in enumerate(("SYN-001", "SYN-002")):
        row = block * 8 + 1
        sheet.cell(row + 1, 1, user)
        sheet.cell(row + 6, 3, "E1")
        sheet.cell(row + 6, 4, "E2")
        sheet.cell(row + 6, 5, "E3")
        sheet.cell(row + 6, 6, "E4")
        for column, value in enumerate(values, 3):
            sheet.cell(row + 7, column, value)
        # These columns have no meaning and must never become evaluations.
        sheet.cell(row + 1, 4, "Synthetic Province")
        sheet.cell(row + 1, 5, "Synthetic Group")
        sheet.cell(row + 1, 6, 99)
    book.save(path)


def _database(path: Path) -> tuple[UUID, UUID]:
    initialize_database(path)
    edition_id, enrollment_id = uuid4(), uuid4()
    second_enrollment_id = uuid4()
    with connection(path) as db:
        db.execute(
            "INSERT INTO course VALUES(?,?,?,?,?,?,?,?)",
            ("c", "Synthetic", "S", None, None, None, None, None),
        )
        db.execute(
            "INSERT INTO edition VALUES(?,?,?,?,?,?)",
            (str(edition_id), "c", "Synthetic edition", None, None, None),
        )
        db.execute("INSERT INTO student VALUES(?,?,?,?)", ("s", "Alumno 001", None, "SYN-001"))
        db.execute("INSERT INTO student VALUES(?,?,?,?)", ("s2", "Alumno 002", None, "SYN-002"))
        db.execute(
            "INSERT INTO enrollment VALUES(?,?,?,?)",
            (str(enrollment_id), "s", str(edition_id), None),
        )
        db.execute(
            "INSERT INTO enrollment VALUES(?,?,?,?)",
            (str(second_enrollment_id), "s2", str(edition_id), None),
        )
        db.execute(
            "INSERT INTO enrollment_external_identity VALUES(?,?,?,?,?)",
            ("dni", "global", "SYN-001", str(edition_id), str(enrollment_id)),
        )
        db.execute(
            "INSERT INTO enrollment_external_identity VALUES(?,?,?,?,?)",
            ("dni", "global", "SYN-002", str(edition_id), str(second_enrollment_id)),
        )
    return edition_id, enrollment_id


def test_parser_reads_every_eight_row_block_and_calculates_mean_on_demand(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.xlsx"
    _workbook(source)
    observations, diagnostics = parse_evaluations_xlsx(source)

    assert not diagnostics
    assert len(observations) == 8
    assert [item.reference for item in observations[:4]] == ["E1", "E2", "E3", "E4"]
    assert observations[0].result_status == "attempted"
    assert observations[3].result_status == "not_attempted"

    from adams_tutoria.evaluations_xlsx import EvaluationPreview

    preview = EvaluationPreview(observations[:4], (), (), 0, 0, 0, 0)
    assert preview.average("SYN-001") == 27.5
    assert preview.global_passed("SYN-001") is False

    source = tmp_path / "passing-average.xlsx"
    _workbook(source, ("100", "100", "", ""))
    passing, passing_diagnostics = parse_evaluations_xlsx(source)
    assert not passing_diagnostics
    passing_preview = EvaluationPreview(passing[:4], (), (), 0, 0, 0, 0)
    assert passing_preview.average("SYN-001") == 50
    assert passing_preview.global_passed("SYN-001") is True


@pytest.mark.parametrize("threshold", ("50", "60", "70"))
def test_allowed_thresholds_are_preserved_and_applied(tmp_path: Path, threshold: str) -> None:
    source = tmp_path / f"threshold-{threshold}.xlsx"
    _workbook(source, (f"50 ({threshold})", "50", "50", "50"))
    observations, diagnostics = parse_evaluations_xlsx(source)
    assert not diagnostics
    assert observations[0].threshold == int(threshold)
    assert observations[0].passed is (threshold == "50")


@pytest.mark.parametrize("value", ("-1", "50 (55)", "101", "bad"))
def test_invalid_states_scores_or_thresholds_reject_the_whole_workbook(
    tmp_path: Path, value: str
) -> None:
    source = tmp_path / "invalid.xlsx"
    _workbook(source, (value, "50", "50", "50"))
    observations, diagnostics = parse_evaluations_xlsx(source)
    assert observations == () or len(observations) < 8
    assert diagnostics


def test_null_is_not_attempted_but_numeric_zero_is_attempted(tmp_path: Path) -> None:
    source = tmp_path / "states.xlsx"
    _workbook(source, (0, None, "", "50"))
    observations, diagnostics = parse_evaluations_xlsx(source)
    assert not diagnostics
    assert observations[0].result_status == "attempted"
    assert observations[0].score == 0
    assert observations[1].result_status == "not_attempted"
    assert observations[2].result_status == "not_attempted"


def test_preview_confirmation_atomicity_idempotence_and_effective_history(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.xlsx"
    database = tmp_path / "synthetic.sqlite3"
    _workbook(source, ("0", "100", "", "100 (70)"))
    edition_id, _ = _database(database)

    preview = import_evaluations_xlsx(source, database, edition_id)
    assert not preview.applied
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 0

    applied = import_evaluations_xlsx(source, database, edition_id, confirm=True)
    assert applied.applied and not applied.idempotent
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 8
        assert db.execute("SELECT COUNT(*) FROM evaluation_history").fetchone()[0] == 8
        assert db.execute("SELECT COUNT(*) FROM enrollment_progress_current").fetchone()[0] == 0
        assert db.execute("SELECT target_type FROM evaluation").fetchone()[0] == "evaluation_item"

    repeat = import_evaluations_xlsx(source, database, edition_id, confirm=True)
    assert repeat.idempotent
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 8
        assert db.execute("SELECT COUNT(*) FROM evaluation_history").fetchone()[0] == 8
        assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 1


def test_preview_distinguishes_additions_changes_unchanged_rejections_and_ambiguities(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.xlsx"
    database = tmp_path / "synthetic.sqlite3"
    _workbook(source, ("10", "20", "30", "40"))
    edition_id, enrollment_id = _database(database)

    first = import_evaluations_xlsx(source, database, edition_id, confirm=True)
    assert first.preview.category_counts == {
        "additions": 8,
        "changes": 0,
        "unchanged": 0,
        "rejected": 0,
        "ambiguities": 0,
    }

    # One value in each repeated block changes; the other six remain unchanged.
    _workbook(source, ("11", "20", "30", "40"))
    changed = import_evaluations_xlsx(source, database, edition_id)
    assert changed.preview.category_counts == {
        "additions": 0,
        "changes": 2,
        "unchanged": 6,
        "rejected": 0,
        "ambiguities": 0,
    }
    assert changed.preview.diagnostics == ()

    # No matching enrollment is a different, explicit diagnosis.
    unknown_book = Workbook()
    unknown_sheet = unknown_book.active
    unknown_sheet.cell(2, 1, "SYN-UNKNOWN")
    for column, reference in enumerate(("E1", "E2", "E3", "E4"), 3):
        unknown_sheet.cell(7, column, reference)
        unknown_sheet.cell(8, column, "10")
    unknown = tmp_path / "unknown.xlsx"
    unknown_book.save(unknown)
    unresolved = import_evaluations_xlsx(unknown, database, edition_id)
    assert unresolved.preview.ambiguities == 0
    assert unresolved.preview.rejected == 1
    assert {item.code for item in unresolved.diagnostics} == {"identity_not_resolved"}

    with connection(database) as db:
        second_enrollment = db.execute(
            "SELECT id FROM enrollment WHERE id != ?", (str(enrollment_id),)
        ).fetchone()[0]
        # Exercise the resolver's defensive ambiguity branch using a synthetic
        # legacy table without the current uniqueness constraint.
        db.execute("ALTER TABLE enrollment_external_identity RENAME TO enrollment_identity_backup")
        db.execute(
            "CREATE TABLE enrollment_external_identity AS "
            "SELECT * FROM enrollment_identity_backup WHERE 0"
        )
        db.execute(
            "INSERT INTO enrollment_external_identity SELECT * FROM enrollment_identity_backup"
        )
        db.execute(
            "INSERT INTO enrollment_external_identity VALUES(?,?,?,?,?)",
            ("dni", "global", "SYN-001", str(edition_id), second_enrollment),
        )
    ambiguous = import_evaluations_xlsx(source, database, edition_id)
    assert ambiguous.preview.ambiguities == 1
    assert any(item.code == "identity_ambiguous" for item in ambiguous.diagnostics)
    assert all(item.message.find("SYN-001") < 0 for item in ambiguous.diagnostics)


def test_rejection_diagnostics_do_not_retain_raw_rows_or_aggregate_evaluations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.xlsx"
    _workbook(source, ("bad-private-looking-value", "50", "50", "50"))
    observations, diagnostics = parse_evaluations_xlsx(source)
    assert observations == () or len(observations) < 8
    assert diagnostics
    assert all("bad-private-looking-value" not in item.message for item in diagnostics)
    assert all("Synthetic Province" not in item.message for item in diagnostics)


def test_ignored_columns_and_aggregates_do_not_create_evaluations(tmp_path: Path) -> None:
    source = tmp_path / "ignored.xlsx"
    database = tmp_path / "ignored.sqlite3"
    _workbook(source)
    book = Workbook()
    sheet = book.active
    sheet.cell(2, 1, "SYN-001")
    for column, reference in enumerate(("E1", "E2", "E3", "E4", "Nota UF"), 3):
        sheet.cell(7, column, reference)
    for column, value in enumerate(("10", "20", "30", "40", "999"), 3):
        sheet.cell(8, column, value)
    # `media` is intentionally outside the four contractual evaluation cells.
    sheet.cell(8, 8, "999")
    book.save(source)
    edition_id, _ = _database(database)
    result = import_evaluations_xlsx(source, database, edition_id, confirm=True)
    assert result.preview.diagnostics == ()
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 4
        assert (
            db.execute("SELECT COUNT(*) FROM evaluation WHERE raw_value = '999'").fetchone()[0] == 0
        )


def test_confirmed_apply_rolls_back_batch_and_evaluations_on_persistence_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.xlsx"
    database = tmp_path / "synthetic.sqlite3"
    _workbook(source)
    edition_id, _ = _database(database)
    with connection(database) as db:
        db.execute(
            "CREATE TRIGGER fail_evaluation_apply AFTER INSERT ON evaluation "
            "BEGIN SELECT RAISE(ABORT, 'synthetic evaluation failure'); END"
        )

    with pytest.raises(Exception, match="synthetic evaluation failure"):
        import_evaluations_xlsx(source, database, edition_id, confirm=True)
    with connection(database) as db:
        assert db.execute("SELECT COUNT(*) FROM evaluation").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM evaluation_history").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0
