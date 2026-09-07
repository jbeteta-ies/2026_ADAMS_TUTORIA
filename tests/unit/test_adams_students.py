"""Synthetic tests for the provisional ADAMS adapter."""

from pathlib import Path

from adams_tutoria.adapters.adams import (
    AdamsStudentEnrollmentAdapter,
    AdamsStudentEnrollmentMapping,
)
from adams_tutoria.import_contract import RejectionCode
from adams_tutoria.tabular_import import read_tabular


def _adapter() -> AdamsStudentEnrollmentAdapter:
    return AdamsStudentEnrollmentAdapter(
        AdamsStudentEnrollmentMapping(
            full_name="name",
            email="mail",
            student_reference="shared_id",
            enrollment_reference="shared_id",
            edition_label="edition",
        )
    )


def test_direct_mapping_preserves_contract_boundary_and_allows_reuse() -> None:
    result = _adapter().adapt(
        [
            {
                "name": "  Student 001 ",
                "mail": "student001@example.invalid",
                "shared_id": " S-1 ",
                "edition": " Spring ",
            }
        ]
    )
    candidate = result.accepted[0]
    assert candidate.enrollment is not None
    assert candidate.enrollment.student is not None
    assert candidate.enrollment.student.name == "Student 001"
    assert candidate.enrollment.student.reference is not None
    assert candidate.enrollment.enrollment_reference is not None
    assert candidate.enrollment.edition is not None
    assert candidate.enrollment.edition.edition_label == "Spring"
    assert candidate.provenance.row_number == 1


def test_missing_edition_evidence_and_unsafe_reference_are_rejected() -> None:
    result = AdamsStudentEnrollmentAdapter(
        AdamsStudentEnrollmentMapping(
            full_name="name", student_reference="shared_id", edition_label="edition"
        )
    ).adapt(
        [
            {"name": "Student 001", "shared_id": "S-1"},
            {"name": "Student 002", "shared_id": {"unexpected": "object"}, "edition": "Spring"},
        ]
    )
    assert not result.accepted
    assert [rejection.code for rejection in result.rejected] == [
        RejectionCode.MISSING_EVIDENCE,
        RejectionCode.MISSING_EVIDENCE,
    ]


def test_csv_reader_to_tabular_row_to_adapter(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.csv"
    source.write_text("name,edition,shared_id\nStudent 001,Spring,S-1\n", encoding="utf-8")
    rows = read_tabular(source).accepted

    result = AdamsStudentEnrollmentAdapter(
        AdamsStudentEnrollmentMapping(
            full_name="name", student_reference="shared_id", edition_label="edition"
        ),
        source_name=source.name,
        source_kind="csv",
    ).adapt(rows)

    assert len(result.accepted) == 1
    assert result.accepted[0].provenance.source_name == "synthetic.csv"
