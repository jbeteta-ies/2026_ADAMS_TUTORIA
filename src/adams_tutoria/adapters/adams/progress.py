"""Provisional adapter for synthetic ADAMS progress rows.

The real ADAMS progress-report shape is intentionally unknown.  This module
therefore accepts an explicit caller-owned mapping and emits only the stable
import contract.  It does not assign a scale, range, rounding rule, or
cumulative meaning to a progress scalar.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from numbers import Real
from uuid import UUID

from adams_tutoria.import_contract import (
    EditionEvidence,
    EnrollmentEvidence,
    ImportCandidate,
    ImportEntity,
    ImportResult,
    Provenance,
    RejectedRow,
    RejectionCode,
    ResolutionReference,
    StudentEvidence,
)


@dataclass(frozen=True, slots=True)
class AdamsProgressMapping:
    """Explicit mapping from an as-yet unconfirmed report to progress data.

    All columns are unset by default: source headers must be supplied by the
    caller after inspecting a particular report.  Column names are confined to
    this adapter and are never emitted in candidate values.
    """

    student_reference: str | None = None
    student_name: str | None = None
    student_email: str | None = None
    enrollment_reference: str | None = None
    edition_reference: str | None = None
    edition_label: str | None = None
    course_reference: str | None = None
    progress_value: str | None = None
    recorded_at: str | None = None

    def __post_init__(self) -> None:
        columns = (
            self.student_reference,
            self.student_name,
            self.student_email,
            self.enrollment_reference,
            self.edition_reference,
            self.edition_label,
            self.course_reference,
            self.progress_value,
            self.recorded_at,
        )
        if any(column is not None and not column.strip() for column in columns):
            raise ValueError("mapped column names must not be blank")
        if self.progress_value is None:
            raise ValueError("progress_value column is required")


type Row = Mapping[str, object]


class AdamsProgressAdapter:
    """Translate tabular rows into source-independent progress candidates."""

    def __init__(
        self,
        mapping: AdamsProgressMapping,
        *,
        source_name: str = "adams-input",
        source_kind: str = "adams-tabular",
    ) -> None:
        self.mapping = mapping
        self._source_name = source_name
        self._source_kind = source_kind
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
                accepted.append(self._candidate(raw_row, provenance))
            except ValueError as error:
                rejected.append(RejectedRow(provenance, RejectionCode.MISSING_EVIDENCE, str(error)))
        return ImportResult(accepted=tuple(accepted), rejected=tuple(rejected))

    def _candidate(self, row: Row, provenance: Provenance) -> ImportCandidate:
        mapping = self.mapping
        student = StudentEvidence(
            reference=self._reference(row, mapping.student_reference),
            name=self._text(row, mapping.student_name),
            email=self._text(row, mapping.student_email),
        )
        edition = EditionEvidence(
            edition_reference=self._reference(row, mapping.edition_reference),
            edition_label=self._text(row, mapping.edition_label),
            course_reference=self._reference(row, mapping.course_reference),
        )
        enrollment = EnrollmentEvidence(
            enrollment_reference=self._reference(row, mapping.enrollment_reference),
            student=student,
            edition=edition,
        )
        if not enrollment.has_evidence:
            raise ValueError("progress row lacks conservative identity evidence")

        values = [("progress_value", self._scalar(row, mapping.progress_value))]
        if mapping.recorded_at is not None and mapping.recorded_at in row:
            timestamp = self._timestamp(row[mapping.recorded_at])
            if timestamp is not None:
                values.append(("recorded_at", timestamp))
        return ImportCandidate(
            ImportEntity.PROGRESS,
            provenance,
            student=student if student.has_evidence else None,
            edition=edition if edition.has_evidence else None,
            enrollment=enrollment if enrollment.has_evidence else None,
            values=tuple(values),
        )

    @staticmethod
    def _value(row: Row, column: str | None) -> object:
        if column is None or column not in row or row[column] is None:
            raise ValueError("required mapped value is missing")
        return row[column]

    @classmethod
    def _text(cls, row: Row, column: str | None) -> str | None:
        if column is None or column not in row or row[column] is None:
            return None
        value = row[column]
        if not isinstance(value, str):
            raise ValueError("text field has an unsafe value")
        value = value.strip()
        return value or None

    @classmethod
    def _reference(cls, row: Row, column: str | None) -> ResolutionReference | None:
        if column is None or column not in row or row[column] is None:
            return None
        value = row[column]
        if isinstance(value, UUID):
            return ResolutionReference(reference=value)
        if isinstance(value, str):
            value = value.strip()
            return ResolutionReference(reference=value) if value else None
        if isinstance(value, Real) and not isinstance(value, bool) and isfinite(float(value)):
            return ResolutionReference(reference=str(value))
        raise ValueError("reference field has an unsafe value")

    @classmethod
    def _scalar(cls, row: Row, column: str | None) -> str:
        value = cls._value(row, column)
        if isinstance(value, bool):
            raise ValueError("progress scalar has an unsafe value")
        if isinstance(value, Real):
            numeric = float(value)
            if not isfinite(numeric):
                raise ValueError("progress scalar is not finite")
            return str(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("progress scalar is empty")
            try:
                decimal = Decimal(text)
            except InvalidOperation as error:
                raise ValueError("progress scalar is not numeric") from error
            if not decimal.is_finite():
                raise ValueError("progress scalar is not finite")
            return text
        raise ValueError("progress scalar has an unsafe value")

    @staticmethod
    def _timestamp(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("timestamp has an unsafe value")
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamp is not a supported ISO-8601 value") from error
        return parsed.isoformat()
