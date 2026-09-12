"""Provisional adapter for synthetic ADAMS student/enrollment rows.

This module is deliberately the only place where ADAMS column names and their
meaning are interpreted.  It stops at :class:`ImportCandidate`: it does not
create domain objects, match records, deduplicate rows, or persist anything.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from numbers import Real
from uuid import UUID

from adams_tutoria.import_contract import (
    EditionEvidence,
    EnrollmentEvidence,
    ExternalStudentIdentity,
    ImportCandidate,
    ImportEntity,
    ImportResult,
    Provenance,
    RejectedRow,
    RejectionCode,
    ResolutionReference,
    StudentEvidence,
)


class FullNameStrategy(StrEnum):
    """How an available full-name column is represented until ADAMS is known."""

    DIRECT = "direct"


@dataclass(frozen=True, slots=True)
class AdamsStudentEnrollmentMapping:
    """Immutable mapping from ADAMS-owned columns to contract evidence.

    Column names may be reused intentionally.  In particular, the same source
    column can supply a student or enrollment reference when a report exposes
    only one identifier.  No universal one-to-one column invariant is imposed.
    """

    full_name: str | None = "full_name"
    email: str | None = "email"
    student_reference: str | None = None
    enrollment_reference: str | None = None
    edition_reference: str | None = None
    edition_label: str | None = None
    course_reference: str | None = None
    full_name_strategy: FullNameStrategy = FullNameStrategy.DIRECT
    external_source: str | None = None
    external_context: str | None = None
    source_student_id: str | None = None
    action: str | None = None
    group: str | None = None

    def __post_init__(self) -> None:
        columns = (
            self.full_name,
            self.email,
            self.student_reference,
            self.enrollment_reference,
            self.edition_reference,
            self.edition_label,
            self.course_reference,
            self.external_source,
            self.external_context,
            self.source_student_id,
        )
        if any(column is not None and not column.strip() for column in columns):
            raise ValueError("mapped column names must not be blank")
        if not isinstance(self.full_name_strategy, FullNameStrategy):
            raise ValueError("unsupported full-name strategy")
        identity_fields = (self.external_source, self.external_context, self.source_student_id)
        if any(field is not None for field in identity_fields) and not all(identity_fields):
            raise ValueError(
                "external identity mapping must define source, context, and student id"
            )
        if self.edition_reference is None and self.edition_label is None:
            raise ValueError("edition_reference or edition_label is required")


type Row = Mapping[str, object]


class AdamsStudentEnrollmentAdapter:
    """Translate tabular rows into enrollment candidates using a fixed mapping."""

    def __init__(
        self,
        mapping: AdamsStudentEnrollmentMapping,
        *,
        source_name: str = "adams-input",
        source_kind: str = "adams-tabular",
    ) -> None:
        self.mapping = mapping
        self._source_name = source_name
        self._source_kind = source_kind
        # Validate before processing rows, while retaining safe provenance only.
        Provenance(source_name, source_kind)

    def adapt(self, rows: Iterable[object]) -> ImportResult[ImportCandidate]:
        accepted: list[ImportCandidate] = []
        rejected: list[RejectedRow] = []
        for row_number, raw_row in enumerate(rows, start=1):
            provenance = Provenance(self._source_name, self._source_kind, row_number=row_number)
            if not isinstance(raw_row, Mapping):
                rejected.append(
                    RejectedRow(provenance, RejectionCode.INVALID, "row is not a tabular mapping")
                )
                continue
            try:
                candidate = self._candidate(raw_row, provenance)
            except ValueError as error:
                rejected.append(RejectedRow(provenance, RejectionCode.MISSING_EVIDENCE, str(error)))
                continue
            accepted.append(candidate)
        return ImportResult(accepted=tuple(accepted), rejected=tuple(rejected))

    def _candidate(self, row: Row, provenance: Provenance) -> ImportCandidate:
        student = StudentEvidence(
            reference=self._reference(row, self.mapping.student_reference),
            name=self._text(row, self.mapping.full_name),
            email=self._text(row, self.mapping.email),
            external_identity=self._identity(row),
        )
        edition = EditionEvidence(
            edition_reference=self._reference(row, self.mapping.edition_reference),
            edition_label=self._text(row, self.mapping.edition_label),
            course_reference=self._reference(row, self.mapping.course_reference),
        )
        enrollment = EnrollmentEvidence(
            enrollment_reference=self._reference(row, self.mapping.enrollment_reference),
            student=student,
            edition=edition,
        )
        return ImportCandidate(
            ImportEntity.ENROLLMENT,
            provenance,
            enrollment=enrollment,
            action=self.mapping.action,
            group=self.mapping.group,
        )

    def _identity(self, row: Row) -> ExternalStudentIdentity | None:
        mapping = self.mapping
        if (
            mapping.external_source is None
            and mapping.external_context is None
            and mapping.source_student_id is None
        ):
            return None
        if not all((mapping.external_source, mapping.external_context, mapping.source_student_id)):
            raise ValueError("external identity mapping is incomplete")
        source = self._text(row, mapping.external_source)
        context = self._text(row, mapping.external_context)
        source_id = self._text(row, mapping.source_student_id)
        if source is None or context is None or source_id is None:
            return None
        return ExternalStudentIdentity(source, context, source_id)

    @staticmethod
    def _text(row: Row, column: str | None) -> str | None:
        if column is None or column not in row or row[column] is None:
            return None
        value = row[column]
        if not isinstance(value, str):
            raise ValueError("text field has an unsafe value")
        value = value.strip()
        return value or None

    @staticmethod
    def _reference(row: Row, column: str | None) -> ResolutionReference | None:
        if column is None or column not in row or row[column] is None:
            return None
        value = row[column]
        if isinstance(value, UUID):
            return ResolutionReference(reference=value)
        if isinstance(value, str):
            value = value.strip()
            return ResolutionReference(reference=value) if value else None
        # XLSX may represent a textual identifier as a numeric scalar.  Only
        # finite real scalars are converted; other types are never guessed at.
        if isinstance(value, Real) and not isinstance(value, bool) and isfinite(float(value)):
            return ResolutionReference(reference=str(value).strip())
        raise ValueError("reference field has an unsafe value")
