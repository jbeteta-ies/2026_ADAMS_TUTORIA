"""Source-independent contract for adapting external imports."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExternalStudentIdentity:
    """Stable student identity scoped by source and context."""

    source: str
    context: str
    source_student_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("source", self.source),
            ("context", self.context),
            ("source_student_id", self.source_student_id),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be blank")

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.context, self.source_student_id)


class ImportEntity(StrEnum):
    STUDENT = "student"
    EDITION = "edition"
    ENROLLMENT = "enrollment"
    PROGRESS = "progress"
    EVALUATION = "evaluation"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Minimal source location information safe for diagnostics."""

    source_name: str
    source_kind: str
    row_number: int | None = None
    source_identifier: str | None = None

    def __post_init__(self) -> None:
        if not self.source_name.strip() or not self.source_kind.strip():
            raise ValueError("source_name and source_kind must not be blank")
        if self.row_number is not None and self.row_number < 1:
            raise ValueError("row_number must be positive")


@dataclass(frozen=True, slots=True)
class ResolutionReference:
    """A flexible application-owned reference or human-readable label."""

    reference: str | UUID | None = None
    label: str | None = None

    @property
    def has_evidence(self) -> bool:
        return self.reference is not None or (self.label is not None and bool(self.label.strip()))

    def __post_init__(self) -> None:
        if self.reference is None and self.label is None:
            raise ValueError("a resolution reference needs reference or label")
        if isinstance(self.reference, str) and not self.reference.strip():
            raise ValueError("reference must not be blank")
        if self.label is not None and not self.label.strip():
            raise ValueError("label must not be blank")


@dataclass(frozen=True, slots=True)
class StudentEvidence:
    reference: ResolutionReference | None = None
    name: str | None = None
    email: str | None = None
    external_identity: ExternalStudentIdentity | None = None

    @property
    def has_evidence(self) -> bool:
        return (
            self.external_identity is not None
            or (self.reference is not None and self.reference.has_evidence)
            or any(value is not None and bool(value.strip()) for value in (self.name, self.email))
        )


@dataclass(frozen=True, slots=True)
class EditionEvidence:
    """Course evidence alone intentionally cannot identify an edition."""

    edition_reference: ResolutionReference | None = None
    edition_label: str | None = None
    course_reference: ResolutionReference | None = None

    @property
    def has_evidence(self) -> bool:
        return (self.edition_reference is not None and self.edition_reference.has_evidence) or (
            self.edition_label is not None and bool(self.edition_label.strip())
        )


@dataclass(frozen=True, slots=True)
class EnrollmentEvidence:
    enrollment_reference: ResolutionReference | None = None
    student: StudentEvidence | None = None
    edition: EditionEvidence | None = None

    @property
    def has_evidence(self) -> bool:
        if self.enrollment_reference is not None and self.enrollment_reference.has_evidence:
            return True
        return (
            self.student is not None
            and self.student.has_evidence
            and self.edition is not None
            and self.edition.has_evidence
        )


@dataclass(frozen=True, slots=True)
class ImportCandidate:
    """A source-independent candidate accepted by an import adapter.

    ``values`` carries optional normalized, application-owned scalar values
    that do not fit the typed evidence fields.  Adapters must keep it free of
    source column names, raw rows, credentials, and personal data that is not
    needed by the downstream contract.  Each key and value must be non-blank;
    source-specific interpretation belongs in the adapter, not in consumers.
    """

    entity: ImportEntity
    provenance: Provenance
    student: StudentEvidence | None = None
    edition: EditionEvidence | None = None
    enrollment: EnrollmentEvidence | None = None
    values: tuple[tuple[str, str], ...] = ()
    action: str | None = None
    group: str | None = None

    def __post_init__(self) -> None:
        if any(not key.strip() or not value.strip() for key, value in self.values):
            raise ValueError("candidate value keys and values must not be blank")
        for field_name, value in (("action", self.action), ("group", self.group)):
            if value is not None and not value.strip():
                raise ValueError(f"{field_name} must be non-blank or None")
        if self.entity is ImportEntity.STUDENT and (
            self.student is None or not self.student.has_evidence
        ):
            raise ValueError("student candidate lacks student evidence")
        if self.entity is ImportEntity.EDITION and (
            self.edition is None or not self.edition.has_evidence
        ):
            raise ValueError("edition candidate needs edition_reference or edition_label")
        if self.entity is ImportEntity.ENROLLMENT and (
            self.enrollment is None or not self.enrollment.has_evidence
        ):
            raise ValueError("enrollment candidate lacks enrollment or student/edition evidence")


class RejectionCode(StrEnum):
    INVALID = "invalid"
    MISSING_EVIDENCE = "missing_evidence"


@dataclass(frozen=True, slots=True)
class RejectedRow:
    provenance: Provenance
    code: RejectionCode
    message: str
    fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("message must not be blank")


@dataclass(frozen=True, slots=True)
class ImportWarning:
    provenance: Provenance
    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise ValueError("warning code and message must not be blank")


CandidateT = TypeVar("CandidateT")


@dataclass(frozen=True, slots=True)
class ImportResult[CandidateT]:
    accepted: tuple[CandidateT, ...] = ()
    rejected: tuple[RejectedRow, ...] = ()
    warnings: tuple[ImportWarning, ...] = ()

    @property
    def partial_success(self) -> bool:
        return bool(self.accepted) and bool(self.rejected)


class ImportAdapter(Protocol):
    def adapt(self, rows: Iterable[object]) -> ImportResult[ImportCandidate]:
        """Translate source-owned input without exposing source columns downstream."""
        ...
