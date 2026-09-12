"""Privacy-safe, source-independent resolution of imported students.

This module deliberately resolves against supplied records only.  It never
matches by name or email and never creates courses or editions.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from adams_tutoria.domain import Edition, Enrollment, Student
from adams_tutoria.import_contract import (
    EditionEvidence,
    ExternalStudentIdentity,
    ImportCandidate,
    ImportEntity,
)


class ResolutionStatus(StrEnum):
    EXISTING = "existing"
    NEW = "new"
    CONFLICT = "conflict"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ResolutionDiagnostic:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ResolutionOutcome:
    status: ResolutionStatus
    student: Student | None = None
    enrollment: Enrollment | None = None
    diagnostic: ResolutionDiagnostic | None = None
    action: str | None = None
    group: str | None = None


class ResolutionLookup(Protocol):
    """Read-only application boundary for existing students and editions."""

    def student_for(self, identity: ExternalStudentIdentity) -> Student | None: ...

    def edition_for(self, evidence: EditionEvidence) -> Edition | None: ...

    def enrollment_for(self, student: Student, edition: Edition) -> Enrollment | None: ...


@dataclass(frozen=True, slots=True)
class InMemoryResolutionLookup:
    """Small synthetic/test lookup; it does not persist or create editions."""

    students: Mapping[tuple[str, str, str], Student] = field(default_factory=dict)
    editions: Mapping[str, Edition] = field(default_factory=dict)
    enrollments: Mapping[tuple[UUID, UUID], Enrollment] = field(default_factory=dict)

    def student_for(self, identity: ExternalStudentIdentity) -> Student | None:
        return self.students.get(identity.key)

    def edition_for(self, evidence: EditionEvidence) -> Edition | None:
        reference = evidence.edition_reference
        if reference is not None:
            key = str(reference.reference) if reference.reference is not None else reference.label
            if key is not None and key in self.editions:
                return self.editions[key]
        if evidence.edition_label is not None:
            return self.editions.get(evidence.edition_label)
        return None

    def enrollment_for(self, student: Student, edition: Edition) -> Enrollment | None:
        return self.enrollments.get((student.id, edition.id))


class ExternalIdentityResolver:
    """Resolve one candidate using only the composite external identity."""

    def __init__(self, lookup: ResolutionLookup) -> None:
        self.lookup = lookup

    def resolve(self, candidate: ImportCandidate) -> ResolutionOutcome:
        if candidate.entity not in (ImportEntity.STUDENT, ImportEntity.ENROLLMENT):
            return self._reject(
                "unsupported_entity", "Candidate entity is not resolvable here", candidate
            )
        evidence = candidate.student or (
            candidate.enrollment.student if candidate.enrollment is not None else None
        )
        if evidence is None or evidence.external_identity is None:
            return self._reject(
                "missing_external_identity", "Composite external identity is required", candidate
            )
        edition_evidence = candidate.edition or (
            candidate.enrollment.edition if candidate.enrollment is not None else None
        )
        if candidate.entity is ImportEntity.ENROLLMENT and edition_evidence is None:
            return self._reject(
                "missing_edition", "Existing edition evidence is required", candidate
            )
        student = self.lookup.student_for(evidence.external_identity)
        if student is None:
            if not evidence.name or not evidence.name.strip():
                return self._reject(
                    "invalid_student_evidence", "New student requires a display name", candidate
                )
            student = Student(uuid4(), evidence.name.strip(), evidence.email)
            student_status = ResolutionStatus.NEW
        else:
            student_status = ResolutionStatus.EXISTING
            if (evidence.name is not None and evidence.name.strip() != student.full_name) or (
                evidence.email is not None and evidence.email.strip() != (student.email or "")
            ):
                return ResolutionOutcome(
                    ResolutionStatus.CONFLICT,
                    student=student,
                    diagnostic=ResolutionDiagnostic(
                        "identity_attributes_conflict",
                        "External identity exists with different descriptive evidence",
                    ),
                    action=candidate.action,
                    group=candidate.group,
                )
        if candidate.entity is ImportEntity.STUDENT:
            return ResolutionOutcome(
                student_status, student=student, action=candidate.action, group=candidate.group
            )
        assert edition_evidence is not None
        edition = self.lookup.edition_for(edition_evidence)
        if edition is None:
            return self._reject("edition_not_found", "Referenced edition does not exist", candidate)
        enrollment = self.lookup.enrollment_for(student, edition)
        if enrollment is not None:
            if student_status is ResolutionStatus.NEW:
                return self._reject(
                    "inconsistent_lookup", "Enrollment points to an unknown student", candidate
                )
            return ResolutionOutcome(
                ResolutionStatus.EXISTING,
                student=student,
                enrollment=enrollment,
                action=candidate.action,
                group=candidate.group,
            )
        return ResolutionOutcome(
            ResolutionStatus.NEW,
            student=student,
            enrollment=Enrollment(uuid4(), student, edition),
            action=candidate.action,
            group=candidate.group,
        )

    @staticmethod
    def _reject(code: str, message: str, candidate: ImportCandidate) -> ResolutionOutcome:
        return ResolutionOutcome(
            ResolutionStatus.REJECTED,
            diagnostic=ResolutionDiagnostic(code, message),
            action=candidate.action,
            group=candidate.group,
        )
