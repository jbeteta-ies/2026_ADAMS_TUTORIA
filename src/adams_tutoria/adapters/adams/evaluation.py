"""Provisional adapter for synthetic ADAMS evaluation rows.

The ADAMS evaluation report shape is not known yet.  Header interpretation is
therefore confined to this module and the caller-provided mapping.  The
adapter emits import candidates only; it does not create domain evaluations,
match identities, apply grading rules, or persist data.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from math import isfinite
from numbers import Real
from types import MappingProxyType
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


class AdamsEvaluationStatus(StrEnum):
    """Contract statuses understood by this provisional adapter."""

    PENDING = "pending"
    COMPLETED = "completed"


type StatusMapping = Mapping[str, str | AdamsEvaluationStatus]


@dataclass(frozen=True, slots=True)
class AdamsEvaluationMapping:
    """Immutable mapping from an unconfirmed report to evaluation fields.

    ``status_mapping`` is mandatory and is copied at construction time.  Its
    values are deliberately limited to pending or completed: a source state
    becomes completed only when it is explicitly mapped to ``COMPLETED``.
    """

    status: str
    student_reference: str | None = None
    student_name: str | None = None
    student_email: str | None = None
    enrollment_reference: str | None = None
    edition_reference: str | None = None
    edition_label: str | None = None
    course_reference: str | None = None
    evaluation_reference: str | None = None
    target_label: str | None = None
    score: str | None = None
    max_score: str | None = None
    passed: str | None = None
    completed_at: str | None = None
    status_mapping: StatusMapping | None = None

    def __post_init__(self) -> None:
        columns = (
            self.student_reference,
            self.student_name,
            self.student_email,
            self.enrollment_reference,
            self.edition_reference,
            self.edition_label,
            self.course_reference,
            self.evaluation_reference,
            self.target_label,
            self.status,
            self.score,
            self.max_score,
            self.passed,
            self.completed_at,
        )
        if any(column is not None and not column.strip() for column in columns):
            raise ValueError("mapped column names must not be blank")
        if not self.status_mapping:
            raise ValueError("status_mapping is required")
        normalized: dict[str, str] = {}
        for source, target in self.status_mapping.items():
            if not isinstance(source, str) or not source.strip():
                raise ValueError("status mapping keys must not be blank")
            try:
                normalized_status = AdamsEvaluationStatus(target).value
            except (TypeError, ValueError) as error:
                raise ValueError("status mapping values must be pending or completed") from error
            normalized[source] = normalized_status
        object.__setattr__(self, "status_mapping", MappingProxyType(normalized))


type Row = Mapping[str, object]


class AdamsEvaluationAdapter:
    """Translate tabular rows into source-independent evaluation candidates."""

    def __init__(
        self,
        mapping: AdamsEvaluationMapping,
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
            raise ValueError("evaluation row lacks conservative identity evidence")

        values: list[tuple[str, str]] = [("status", self._status(row))]
        target_values: list[tuple[str, str]] = []
        if self._present(row, mapping.evaluation_reference):
            values.append(
                ("evaluation_reference", self._reference_value(row, mapping.evaluation_reference))
            )
        if self._present(row, mapping.target_label):
            values.append(("target_label", self._text_required(row, mapping.target_label)))
        target_values = values[1:]
        for name, column in (("score", mapping.score), ("max_score", mapping.max_score)):
            if self._present(row, column):
                assert column is not None
                values.append((name, self._scalar(row[column])))
        if self._present(row, mapping.passed):
            assert mapping.passed is not None
            values.append(("passed", self._boolean(row[mapping.passed])))
        if self._present(row, mapping.completed_at):
            assert mapping.completed_at is not None
            values.append(("completed_at", self._timestamp(row[mapping.completed_at])))
        if (
            mapping.evaluation_reference is not None or mapping.target_label is not None
        ) and not target_values:
            raise ValueError("evaluation row lacks target evidence")
        if mapping.evaluation_reference is None and mapping.target_label is None:
            raise ValueError("evaluation row lacks target evidence mapping")
        return ImportCandidate(
            ImportEntity.EVALUATION,
            provenance,
            student=student if student.has_evidence else None,
            edition=edition if edition.has_evidence else None,
            enrollment=enrollment,
            values=tuple(values),
        )

    def _status(self, row: Row) -> str:
        value = self._value(row, self.mapping.status)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("evaluation status is empty or unsafe")
        try:
            status_mapping = self.mapping.status_mapping
            assert status_mapping is not None
            return status_mapping[value.strip()]
        except KeyError as error:
            raise ValueError("evaluation status is not configured") from error

    @staticmethod
    def _value(row: Row, column: str) -> object:
        if column not in row or row[column] is None:
            raise ValueError("required mapped value is missing")
        return row[column]

    @classmethod
    def _present(cls, row: Row, column: str | None) -> bool:
        return column is not None and column in row and row[column] is not None

    @classmethod
    def _text(cls, row: Row, column: str | None) -> str | None:
        if not cls._present(row, column):
            return None
        assert column is not None
        value = row[column]
        if not isinstance(value, str):
            raise ValueError("text field has an unsafe value")
        return value.strip() or None

    @classmethod
    def _text_required(cls, row: Row, column: str | None) -> str:
        value = cls._text(row, column)
        if value is None:
            raise ValueError("mapped text value is empty")
        return value

    @classmethod
    def _reference(cls, row: Row, column: str | None) -> ResolutionReference | None:
        if not cls._present(row, column):
            return None
        assert column is not None
        value = row[column]
        if isinstance(value, UUID):
            return ResolutionReference(reference=value)
        if isinstance(value, str):
            return ResolutionReference(reference=value.strip()) if value.strip() else None
        if isinstance(value, Real) and not isinstance(value, bool) and isfinite(float(value)):
            return ResolutionReference(reference=str(value))
        raise ValueError("reference field has an unsafe value")

    @classmethod
    def _reference_value(cls, row: Row, column: str | None) -> str:
        reference = cls._reference(row, column)
        if reference is None or reference.reference is None:
            raise ValueError("evaluation reference is empty")
        return str(reference.reference)

    @staticmethod
    def _scalar(value: object) -> str:
        if isinstance(value, bool):
            raise ValueError("score has an unsafe value")
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("score is not finite")
            return str(value)
        if isinstance(value, Real):
            if not isfinite(float(value)):
                raise ValueError("score is not finite")
            return str(value)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            try:
                decimal = Decimal(text)
            except InvalidOperation as error:
                raise ValueError("score is not numeric") from error
            if not decimal.is_finite():
                raise ValueError("score is not finite")
            return text
        raise ValueError("score has an unsafe value")

    @staticmethod
    def _boolean(value: object) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return value.strip().lower()
        raise ValueError("passed has an unsafe value")

    @staticmethod
    def _timestamp(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("completed_at has an unsafe value")
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).isoformat()
        except ValueError as error:
            raise ValueError("completed_at is not a supported ISO-8601 value") from error
