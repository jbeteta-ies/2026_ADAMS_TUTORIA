"""Synthetic tests for the source-independent import contract."""

from uuid import uuid4

import pytest

from adams_tutoria.import_contract import (
    EditionEvidence,
    EnrollmentEvidence,
    ImportCandidate,
    ImportEntity,
    ImportResult,
    ImportWarning,
    Provenance,
    RejectedRow,
    RejectionCode,
    ResolutionReference,
    StudentEvidence,
)


def _provenance() -> Provenance:
    return Provenance("synthetic-input", "fixture", row_number=4)


def test_resolution_reference_accepts_reference_or_label() -> None:
    assert ResolutionReference(reference=uuid4()).has_evidence
    assert ResolutionReference(label="Spring 2026").has_evidence


def test_course_reference_alone_does_not_qualify_edition() -> None:
    evidence = EditionEvidence(course_reference=ResolutionReference(label="Synthetic course"))
    assert not evidence.has_evidence
    with pytest.raises(ValueError, match="edition_reference"):
        ImportCandidate(ImportEntity.EDITION, _provenance(), edition=evidence)


def test_student_candidate_requires_student_evidence() -> None:
    with pytest.raises(ValueError, match="student evidence"):
        ImportCandidate(ImportEntity.STUDENT, _provenance())
    with pytest.raises(ValueError, match="student evidence"):
        ImportCandidate(ImportEntity.STUDENT, _provenance(), student=StudentEvidence())


@pytest.mark.parametrize("values", [(" ", "normalized"), ("normalized", " ")])
def test_candidate_values_reject_blank_keys_or_values(values: tuple[str, str]) -> None:
    with pytest.raises(ValueError, match="value"):
        ImportCandidate(ImportEntity.PROGRESS, _provenance(), values=(values,))


def test_edition_label_qualifies_edition() -> None:
    evidence = EditionEvidence(edition_label="Synthetic spring")
    assert evidence.has_evidence
    ImportCandidate(ImportEntity.EDITION, _provenance(), edition=evidence)


def test_enrollment_requires_reference_or_student_and_edition() -> None:
    student = StudentEvidence(name="Synthetic Student")
    edition = EditionEvidence(edition_label="Synthetic spring")
    assert EnrollmentEvidence(student=student, edition=edition).has_evidence
    assert not EnrollmentEvidence(student=student).has_evidence
    assert EnrollmentEvidence(
        enrollment_reference=ResolutionReference(reference="enr-1")
    ).has_evidence
    with pytest.raises(ValueError, match="enrollment"):
        ImportCandidate(ImportEntity.ENROLLMENT, _provenance())


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("source_name", "source_name"),
        ("source_kind", "source_kind"),
        ("row_number", "row_number"),
    ],
)
def test_invalid_provenance_is_rejected(case: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        if case == "source_name":
            Provenance("", "fixture")
        elif case == "source_kind":
            Provenance("synthetic", "")
        else:
            Provenance("synthetic", "fixture", row_number=0)


@pytest.mark.parametrize(
    "kwargs",
    [{"reference": "   "}, {"label": "   "}],
)
def test_blank_resolution_reference_values_are_rejected(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="blank"):
        ResolutionReference(**kwargs)


def test_blank_rejected_row_message_is_rejected() -> None:
    with pytest.raises(ValueError, match="message"):
        RejectedRow(_provenance(), RejectionCode.INVALID, " ")


@pytest.mark.parametrize(
    ("code", "message"),
    [(" ", "warning"), ("warning", " ")],
)
def test_blank_warning_code_or_message_is_rejected(code: str, message: str) -> None:
    with pytest.raises(ValueError, match="warning"):
        ImportWarning(_provenance(), code, message)


def test_result_preserves_partial_success_and_safe_diagnostics() -> None:
    warning = ImportWarning(_provenance(), "ambiguous", "More than one safe candidate matched")
    rejected = RejectedRow(
        _provenance(), RejectionCode.MISSING_EVIDENCE, "Edition evidence is required"
    )
    result = ImportResult(
        accepted=("synthetic-candidate",), rejected=(rejected,), warnings=(warning,)
    )
    assert result.partial_success
    assert rejected.fields == ()
    assert not hasattr(rejected, "raw_row")
