"""Synthetic tests for the configurable internal spreadsheet contracts."""

from decimal import Decimal

from adams_tutoria.excel_contract import (
    EvaluationExcelAdapter,
    EvaluationExcelColumns,
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
