"""Synthetic tests for the configurable internal spreadsheet contracts."""

from decimal import Decimal

from adams_tutoria.excel_contract import (
    EvaluationExcelAdapter,
    EvaluationExcelColumns,
    EvaluationResultStatus,
    EvaluationStatus,
    ProgressExcelAdapter,
    ProgressExcelColumns,
    StudentExcelAdapter,
    StudentExcelColumns,
)


def test_student_contract_scopes_identity_and_keeps_nullable_metadata() -> None:
    result = StudentExcelAdapter(
        StudentExcelColumns(
            "name", "email", "source", "context", "sid", action="action", group="group"
        ),
        source_name="synthetic.xlsx",
    ).adapt(
        [
            {
                "name": "Alumno 001",
                "email": "alumno001@example.invalid",
                "source": "s",
                "context": "c",
                "sid": "1",
                "action": None,
                "group": None,
            }
        ]
    )

    assert not result.rejected
    assert result.accepted[0].identity is not None
    assert result.accepted[0].identity.key == ("s", "c", "1")
    assert result.accepted[0].action is None


def test_progress_and_evaluation_allow_partial_success() -> None:
    progress = ProgressExcelAdapter(ProgressExcelColumns(progress="p", enrollment_id="en"))
    progress_result = progress.adapt([{"p": "42.5", "en": "en-1"}, {"p": "bad", "en": "en-2"}])
    assert progress_result.partial_success
    assert progress_result.accepted[0].progress == Decimal("42.5")
    assert progress_result.rejected[0].provenance.row_number == 2

    evaluation = EvaluationExcelAdapter(
        EvaluationExcelColumns(
            status="state",
            status_values=(("open", EvaluationStatus.PENDING),),
            enrollment_id="en",
            target="target",
        )
    )
    result = evaluation.adapt([{"state": "open", "en": "en-1", "target": None}])
    assert len(result.accepted) == 1
    assert result.accepted[0].target is None


def test_raw_values_are_bounded_and_never_the_full_row() -> None:
    result = StudentExcelAdapter(StudentExcelColumns(name="name", raw_columns=("name",))).adapt(
        [{"name": "Alumno 002", "secret": "not selected"}]
    )
    assert result.accepted[0].raw_values == (("name", "Alumno 002"),)


def test_evaluation_result_semantics_are_separate_from_lifecycle() -> None:
    adapter = EvaluationExcelAdapter(
        EvaluationExcelColumns(
            status="state",
            status_values=(("open", EvaluationStatus.PENDING),),
            enrollment_id="en",
            score="result",
            max_score="maximum",
            scale="scale",
        )
    )
    result = adapter.adapt(
        [
            {"state": "open", "en": "en-1", "result": '"'},
            {"state": "open", "en": "en-2", "result": 0, "maximum": 10},
            {"state": "open", "en": "en-3", "result": "", "maximum": 10},
            {"state": "open", "en": "en-4", "result": " 7.5 ", "scale": "percent"},
            {"state": "open", "en": "en-5", "result": "n/a"},
        ]
    )
    records = result.accepted
    assert records[0].result.status is EvaluationResultStatus.NOT_ATTEMPTED
    assert records[0].result.raw_value == '"'
    assert records[1].result.status is EvaluationResultStatus.ATTEMPTED
    assert records[1].result.numeric_value == Decimal("0")
    assert records[1].result.maximum == Decimal("10")
    assert records[2].result.status is EvaluationResultStatus.UNKNOWN
    assert records[2].result.raw_value == ""
    assert records[3].result.numeric_value == Decimal("7.5")
    assert records[3].result.raw_value == " 7.5 "
    assert records[3].result.scale == "percent"
    assert records[4].result.status is EvaluationResultStatus.UNKNOWN
    assert all(record.passed is None for record in records)


def test_missing_and_unknown_scales_are_not_normalized() -> None:
    adapter = EvaluationExcelAdapter(
        EvaluationExcelColumns(
            status="state",
            status_values=(("open", EvaluationStatus.PENDING),),
            enrollment_id="en",
            score="result",
            scale="scale",
        )
    )
    result = adapter.adapt(
        [
            {"state": "open", "en": "en-1", "result": 25, "scale": "percent"},
            {"state": "open", "en": "en-2", "result": 25, "scale": "vendor-scale"},
            {"state": "open", "en": "en-3", "result": 25},
        ]
    )

    records = result.accepted
    assert [record.result.scale for record in records] == ["percent", "vendor-scale", None]
    assert [record.result.numeric_value for record in records] == [
        Decimal("25"),
        Decimal("25"),
        Decimal("25"),
    ]
