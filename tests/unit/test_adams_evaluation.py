"""Synthetic tests for the provisional ADAMS evaluation adapter."""

from pathlib import Path

from openpyxl import Workbook

from adams_tutoria.adapters.adams import (
    AdamsEvaluationAdapter,
    AdamsEvaluationMapping,
    AdamsEvaluationStatus,
)
from adams_tutoria.import_contract import ImportEntity, RejectionCode
from adams_tutoria.tabular_import import read_tabular


def _mapping(status_mapping: dict[str, str] | None = None) -> AdamsEvaluationMapping:
    return AdamsEvaluationMapping(
        status="state",
        student_reference="student_key",
        edition_label="edition",
        target_label="activity",
        score="score",
        passed="passed",
        completed_at="done_at",
        status_mapping=status_mapping or {"OPEN": "pending", "DONE": "completed"},
    )


def test_configured_target_fields_require_usable_evidence() -> None:
    mapping = _mapping()
    result = AdamsEvaluationAdapter(mapping).adapt(
        [
            {"student_key": "Student-001", "edition": "Spring", "state": "OPEN"},
            {
                "student_key": "Student-002",
                "edition": "Spring",
                "activity": None,
                "state": "OPEN",
            },
        ]
    )
    assert result.accepted == ()
    assert len(result.rejected) == 2


def test_evaluation_reference_is_valid_target_evidence() -> None:
    mapping = AdamsEvaluationMapping(
        status="state",
        student_reference="student_key",
        edition_label="edition",
        evaluation_reference="evaluation_key",
        status_mapping={"OPEN": "pending"},
    )
    result = AdamsEvaluationAdapter(mapping).adapt(
        [
            {
                "student_key": "Student-001",
                "edition": "Spring",
                "evaluation_key": "Evaluation-001",
                "state": "OPEN",
            }
        ]
    )
    assert len(result.accepted) == 1
    assert ("evaluation_reference", "Evaluation-001") in result.accepted[0].values


def test_evaluation_mapping_is_copied_and_status_is_explicit() -> None:
    statuses = {"OPEN": "pending"}
    mapping = _mapping(statuses)
    statuses["OPEN"] = "completed"
    result = AdamsEvaluationAdapter(mapping).adapt(
        [
            {
                "student_key": "Student-001",
                "edition": "Spring",
                "activity": "Quiz A",
                "state": "OPEN",
                "score": 9,
            }
        ]
    )
    assert result.accepted[0].entity is ImportEntity.EVALUATION
    assert ("status", AdamsEvaluationStatus.PENDING) in result.accepted[0].values
    assert mapping.status_mapping == {"OPEN": "pending"}


def test_result_fields_never_imply_completed_and_unknown_status_is_rejected() -> None:
    result = AdamsEvaluationAdapter(_mapping()).adapt(
        [
            {
                "student_key": "Student-001",
                "edition": "Spring",
                "activity": "Quiz A",
                "state": "OPEN",
                "score": 10,
                "passed": True,
                "done_at": "2026-02-01T00:00:00Z",
            },
            {
                "student_key": "Student-002",
                "edition": "Spring",
                "activity": "Quiz A",
                "state": "UNSEEN",
                "score": 10,
            },
        ]
    )
    assert ("status", "pending") in result.accepted[0].values
    assert ("completed_at", "2026-02-01T00:00:00+00:00") in result.accepted[0].values
    assert result.rejected[0].code is RejectionCode.MISSING_EVIDENCE


def test_csv_and_xlsx_reader_rows_feed_the_adapter(tmp_path: Path) -> None:
    csv_source = tmp_path / "synthetic-evaluations.csv"
    csv_source.write_text(
        "student_key,edition,activity,state\nStudent-001,Spring,Quiz A,DONE\n",
        encoding="utf-8",
    )
    csv_rows = read_tabular(csv_source).accepted
    csv_result = AdamsEvaluationAdapter(_mapping(), source_name=csv_source.name).adapt(csv_rows)
    assert csv_result.accepted[0].provenance.source_name == csv_source.name

    xlsx_source = tmp_path / "synthetic-evaluations.xlsx"
    workbook = Workbook()
    workbook.active.append(["student_key", "edition", "activity", "state"])
    workbook.active.append(["Student-002", "Spring", "Quiz B", "OPEN"])
    workbook.save(xlsx_source)
    xlsx_rows = read_tabular(xlsx_source).accepted
    xlsx_result = AdamsEvaluationAdapter(_mapping(), source_name=xlsx_source.name).adapt(xlsx_rows)
    assert ("status", "pending") in xlsx_result.accepted[0].values
