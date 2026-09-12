"""Synthetic tests for composite external identity resolution."""

from uuid import uuid4

from adams_tutoria.domain import Course, Edition, Enrollment, Student
from adams_tutoria.identity_resolution import (
    ExternalIdentityResolver,
    InMemoryResolutionLookup,
    ResolutionStatus,
)
from adams_tutoria.import_contract import (
    EditionEvidence,
    EnrollmentEvidence,
    ExternalStudentIdentity,
    ImportCandidate,
    ImportEntity,
    Provenance,
    StudentEvidence,
)


def _candidate(identity: ExternalStudentIdentity, *, edition: str | None = None) -> ImportCandidate:
    student = StudentEvidence(external_identity=identity, name="Synthetic Student")
    if edition is None:
        return ImportCandidate(
            ImportEntity.STUDENT, Provenance("fixture", "synthetic"), student=student
        )
    return ImportCandidate(
        ImportEntity.ENROLLMENT,
        Provenance("fixture", "synthetic"),
        enrollment=EnrollmentEvidence(
            student=student,
            edition=EditionEvidence(edition_label=edition),
        ),
    )


def test_identity_is_scoped_by_source_and_context() -> None:
    identity = ExternalStudentIdentity("system-a", "edition-1", "S-1")
    student = Student(uuid4(), "Synthetic Student")
    result = ExternalIdentityResolver(
        InMemoryResolutionLookup(students={identity.key: student})
    ).resolve(_candidate(identity))
    assert result.status is ResolutionStatus.EXISTING
    assert result.student == student


def test_new_student_and_existing_edition_create_no_course_or_edition() -> None:
    course = Course(uuid4(), "Synthetic Course")
    edition = Edition(uuid4(), course, "Synthetic Edition")
    result = ExternalIdentityResolver(
        InMemoryResolutionLookup(editions={"Synthetic Edition": edition})
    ).resolve(
        _candidate(
            ExternalStudentIdentity("system-a", "edition-1", "S-2"), edition="Synthetic Edition"
        )
    )
    assert result.status is ResolutionStatus.NEW
    assert result.enrollment is not None
    assert result.enrollment.edition is edition


def test_missing_edition_is_rejected_without_name_or_email_matching() -> None:
    student = Student(uuid4(), "Synthetic Student", "student@example.invalid")
    identity = ExternalStudentIdentity("system-a", "edition-1", "S-1")
    result = ExternalIdentityResolver(
        InMemoryResolutionLookup(students={identity.key: student})
    ).resolve(_candidate(identity, edition="Absent Edition"))
    assert result.status is ResolutionStatus.REJECTED
    assert result.diagnostic is not None
    assert "Synthetic" not in result.diagnostic.message


def test_action_and_group_are_nullable_and_safe() -> None:
    candidate = _candidate(ExternalStudentIdentity("system-a", "edition-1", "S-3"))
    assert candidate.action is None and candidate.group is None


def test_existing_enrollment_is_returned_without_creating_another() -> None:
    identity = ExternalStudentIdentity("system-a", "edition-1", "S-4")
    student = Student(uuid4(), "Synthetic Student")
    course = Course(uuid4(), "Synthetic Course")
    edition = Edition(uuid4(), course, "Synthetic Edition")
    enrollment = Enrollment(uuid4(), student, edition)
    result = ExternalIdentityResolver(
        InMemoryResolutionLookup(
            students={identity.key: student},
            editions={"Synthetic Edition": edition},
            enrollments={(student.id, edition.id): enrollment},
        )
    ).resolve(_candidate(identity, edition="Synthetic Edition"))
    assert result.status is ResolutionStatus.EXISTING
    assert result.enrollment is enrollment


def test_conflicting_descriptive_attributes_are_rejected_without_matching() -> None:
    identity = ExternalStudentIdentity("system-a", "edition-1", "S-5")
    student = Student(uuid4(), "Stored Student", "stored@example.invalid")
    candidate = ImportCandidate(
        ImportEntity.STUDENT,
        Provenance("fixture", "synthetic"),
        student=StudentEvidence(
            external_identity=identity,
            name="Different Student",
            email="different@example.invalid",
        ),
    )
    result = ExternalIdentityResolver(
        InMemoryResolutionLookup(students={identity.key: student})
    ).resolve(candidate)
    assert result.status is ResolutionStatus.CONFLICT
    assert result.diagnostic is not None
    assert result.diagnostic.code == "identity_attributes_conflict"


def test_invalid_new_student_evidence_is_rejected() -> None:
    identity = ExternalStudentIdentity("system-a", "edition-1", "S-6")
    candidate = ImportCandidate(
        ImportEntity.STUDENT,
        Provenance("fixture", "synthetic"),
        student=StudentEvidence(external_identity=identity),
    )
    result = ExternalIdentityResolver(InMemoryResolutionLookup()).resolve(candidate)
    assert result.status is ResolutionStatus.REJECTED
    assert result.diagnostic is not None
    assert result.diagnostic.code == "invalid_student_evidence"


def test_missing_identity_is_rejected_even_when_name_and_email_exist() -> None:
    candidate = ImportCandidate(
        ImportEntity.STUDENT,
        Provenance("fixture", "synthetic"),
        student=StudentEvidence(name="Synthetic Student", email="student@example.invalid"),
    )
    result = ExternalIdentityResolver(InMemoryResolutionLookup()).resolve(candidate)
    assert result.status is ResolutionStatus.REJECTED
    assert result.diagnostic is not None
    assert result.diagnostic.code == "missing_external_identity"


def test_unsupported_entity_is_rejected() -> None:
    candidate = ImportCandidate(
        ImportEntity.EDITION,
        Provenance("fixture", "synthetic"),
        edition=EditionEvidence(edition_label="Synthetic Edition"),
    )
    result = ExternalIdentityResolver(InMemoryResolutionLookup()).resolve(candidate)
    assert result.status is ResolutionStatus.REJECTED
    assert result.diagnostic is not None
    assert result.diagnostic.code == "unsupported_entity"


def test_action_and_group_propagate_through_resolution() -> None:
    identity = ExternalStudentIdentity("system-a", "edition-1", "S-7")
    candidate = ImportCandidate(
        ImportEntity.STUDENT,
        Provenance("fixture", "synthetic"),
        student=StudentEvidence(external_identity=identity, name="Synthetic Student"),
        action="review",
        group="cohort-a",
    )
    result = ExternalIdentityResolver(InMemoryResolutionLookup()).resolve(candidate)
    assert result.status is ResolutionStatus.NEW
    assert result.action == "review"
    assert result.group == "cohort-a"
