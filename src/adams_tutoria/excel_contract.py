"""Typed, source-independent contracts for spreadsheet imports.

The column names in this module are configuration, not a claim about an
official ADAMS export.  Adapters read a mapping row and emit one typed record
per row.  A bad row is isolated in the :class:`ImportResult`; the raw row is
never put in a diagnostic or in a contract record.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from numbers import Real
from typing import TypeVar

from adams_tutoria.import_contract import (
    ExternalStudentIdentity,
    ImportResult,
    ImportWarning,
    Provenance,
    RejectedRow,
    RejectionCode,
)

type Row = Mapping[str, object]
type RawValues = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class StudentExcelColumns:
    """Explicit mapping for a student sheet; all names are caller supplied."""

    name: str | None = None
    email: str | None = None
    source: str | None = None
    context: str | None = None
    student_id: str | None = None
    action: str | None = None
    group: str | None = None
    raw_columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProgressExcelColumns:
    """Explicit mapping for an evolution/progress sheet."""

    progress: str | None = None
    name: str | None = None
    email: str | None = None
    source: str | None = None
    context: str | None = None
    student_id: str | None = None
    enrollment_id: str | None = None
    edition_id: str | None = None
    node_id: str | None = None
    edition_label: str | None = None
    recorded_at: str | None = None
    action: str | None = None
    group: str | None = None
    raw_columns: tuple[str, ...] = ()


class EvaluationStatus(StrEnum):
    """Lifecycle state of the evaluation record, not its result."""

    PENDING = "pending"
    COMPLETED = "completed"


class EvaluationResultStatus(StrEnum):
    """Semantic state of an observed evaluation result."""

    NOT_ATTEMPTED = "not_attempted"
    ATTEMPTED = "attempted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """A result observation without grading or pass/fail inference.

    ``raw_value`` is retained as supplied. ``scale`` is descriptive only: an
    explicitly supplied percentage is not converted, and an unknown scale is
    never normalised.
    """

    status: EvaluationResultStatus
    raw_value: str | None = None
    numeric_value: Decimal | None = None
    maximum: Decimal | None = None
    scale: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationExcelColumns:
    """Explicit mapping for an evaluation sheet.

    ``status_values`` is required because source status labels are not
    assumed.  Scores, pass/fail and completion time remain nullable.
    """

    status: str | None = None
    status_values: tuple[tuple[str, EvaluationStatus], ...] = ()
    target: str | None = None
    evaluation_id: str | None = None
    score: str | None = None
    max_score: str | None = None
    passed: str | None = None
    completed_at: str | None = None
    name: str | None = None
    email: str | None = None
    source: str | None = None
    context: str | None = None
    student_id: str | None = None
    enrollment_id: str | None = None
    edition_id: str | None = None
    edition_label: str | None = None
    action: str | None = None
    group: str | None = None
    raw_columns: tuple[str, ...] = ()
    scale: str | None = None


@dataclass(frozen=True, slots=True)
class StudentRecord:
    identity: ExternalStudentIdentity | None
    name: str | None
    email: str | None
    action: str | None = None
    group: str | None = None
    provenance: Provenance | None = None
    raw_values: RawValues = ()


@dataclass(frozen=True, slots=True)
class ProgressRecord:
    progress: Decimal
    identity: ExternalStudentIdentity | None = None
    name: str | None = None
    email: str | None = None
    enrollment_id: str | None = None
    edition_id: str | None = None
    edition_label: str | None = None
    recorded_at: datetime | None = None
    node_id: str | None = None
    action: str | None = None
    group: str | None = None
    provenance: Provenance | None = None
    raw_values: RawValues = ()


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    status: EvaluationStatus
    target: str | None = None
    evaluation_id: str | None = None
    score: Decimal | None = None
    max_score: Decimal | None = None
    passed: bool | None = None
    completed_at: datetime | None = None
    identity: ExternalStudentIdentity | None = None
    name: str | None = None
    email: str | None = None
    enrollment_id: str | None = None
    edition_id: str | None = None
    edition_label: str | None = None
    action: str | None = None
    group: str | None = None
    provenance: Provenance | None = None
    raw_values: RawValues = ()
    result: EvaluationResult = EvaluationResult(EvaluationResultStatus.UNKNOWN)


RecordT = TypeVar("RecordT")


class _Adapter[RecordT]:
    def __init__(self, *, source_name: str, source_kind: str) -> None:
        self.source_name = source_name
        self.source_kind = source_kind
        Provenance(source_name, source_kind)

    def adapt(self, rows: Iterable[object]) -> ImportResult[RecordT]:
        accepted: list[RecordT] = []
        rejected: list[RejectedRow] = []
        warnings: list[ImportWarning] = []
        for number, value in enumerate(rows, 1):
            provenance = Provenance(self.source_name, self.source_kind, row_number=number)
            if not isinstance(value, Mapping):
                rejected.append(
                    RejectedRow(provenance, RejectionCode.INVALID, "row is not tabular")
                )
                continue
            try:
                accepted.append(self._record(value, provenance))
            except ValueError as error:
                rejected.append(RejectedRow(provenance, RejectionCode.INVALID, str(error)))
        return ImportResult(tuple(accepted), tuple(rejected), tuple(warnings))

    def _record(self, row: Row, provenance: Provenance) -> RecordT:
        raise NotImplementedError


class StudentExcelAdapter(_Adapter[StudentRecord]):
    def __init__(
        self,
        columns: StudentExcelColumns,
        *,
        source_name: str = "excel-input",
        source_kind: str = "xlsx",
    ) -> None:
        self.columns = columns
        for item in fields(columns):
            value = getattr(columns, item.name)
            if isinstance(value, str):
                _column_name(value)
        super().__init__(source_name=source_name, source_kind=source_kind)

    def _record(self, row: Row, provenance: Provenance) -> StudentRecord:
        c = self.columns
        identity = _identity(row, c.source, c.context, c.student_id)
        name, email = _text(row, c.name), _text(row, c.email)
        if identity is None and name is None and email is None:
            raise ValueError("student row lacks identity or descriptive evidence")
        return StudentRecord(
            identity,
            name,
            email,
            _text(row, c.action),
            _text(row, c.group),
            provenance,
            _raw(row, c.raw_columns),
        )


class ProgressExcelAdapter(_Adapter[ProgressRecord]):
    def __init__(
        self,
        columns: ProgressExcelColumns,
        *,
        source_name: str = "excel-input",
        source_kind: str = "xlsx",
    ) -> None:
        self.columns = columns
        for item in fields(columns):
            value = getattr(columns, item.name)
            if isinstance(value, str):
                _column_name(value)
        super().__init__(source_name=source_name, source_kind=source_kind)

    def _record(self, row: Row, provenance: Provenance) -> ProgressRecord:
        c = self.columns
        progress = _decimal(row, c.progress, required=True)
        assert progress is not None
        identity = _identity(row, c.source, c.context, c.student_id)
        enrollment_id, edition_id = _text(row, c.enrollment_id), _text(row, c.edition_id)
        if identity is None and enrollment_id is None:
            raise ValueError("progress row lacks scoped student or enrollment identity")
        return ProgressRecord(
            progress,
            identity,
            _text(row, c.name),
            _text(row, c.email),
            enrollment_id,
            edition_id,
            _text(row, c.edition_label),
            _timestamp(row, c.recorded_at),
            _text(row, c.node_id),
            _text(row, c.action),
            _text(row, c.group),
            provenance,
            _raw(row, c.raw_columns),
        )


class EvaluationExcelAdapter(_Adapter[EvaluationRecord]):
    def __init__(
        self,
        columns: EvaluationExcelColumns,
        *,
        source_name: str = "excel-input",
        source_kind: str = "xlsx",
    ) -> None:
        self.columns = columns
        for item in fields(columns):
            value = getattr(columns, item.name)
            if isinstance(value, str):
                _column_name(value)
        super().__init__(source_name=source_name, source_kind=source_kind)

    def _record(self, row: Row, provenance: Provenance) -> EvaluationRecord:
        c = self.columns
        if c.status is None or row.get(c.status) is None:
            raise ValueError("evaluation status is required")
        source_status = str(row[c.status]).strip()
        statuses = dict(c.status_values)
        if source_status not in statuses:
            raise ValueError("evaluation status is not configured")
        identity = _identity(row, c.source, c.context, c.student_id)
        enrollment_id = _text(row, c.enrollment_id)
        if identity is None and enrollment_id is None:
            raise ValueError("evaluation row lacks scoped student or enrollment identity")
        raw_score = _result(row, c.score, _text(row, c.scale))
        score = raw_score.numeric_value
        max_score = _decimal(row, c.max_score)
        passed = _text(row, c.passed)
        passed_value = None if passed is None else passed.lower() in {"true", "yes", "1"}
        if passed is not None and passed.lower() not in {"true", "false", "yes", "no", "1", "0"}:
            raise ValueError("passed value is invalid")
        return EvaluationRecord(
            statuses[source_status],
            target=_text(row, c.target),
            evaluation_id=_text(row, c.evaluation_id),
            score=score,
            max_score=max_score,
            passed=passed_value,
            completed_at=_timestamp(row, c.completed_at),
            identity=identity,
            name=_text(row, c.name),
            email=_text(row, c.email),
            enrollment_id=enrollment_id,
            edition_id=_text(row, c.edition_id),
            edition_label=_text(row, c.edition_label),
            action=_text(row, c.action),
            group=_text(row, c.group),
            provenance=provenance,
            raw_values=_raw(row, c.raw_columns),
            result=EvaluationResult(
                raw_score.status,
                raw_score.raw_value,
                raw_score.numeric_value,
                max_score,
                raw_score.scale,
            ),
        )


def _column_name(value: str | None) -> None:
    if value is not None and not value.strip():
        raise ValueError("configured column names must not be blank")


def _text(row: Row, column: str | None) -> str | None:
    if column is None or row.get(column) is None:
        return None
    value = row[column]
    if not isinstance(value, str):
        raise ValueError("text value is unsafe")
    return value.strip() or None


def _identity(
    row: Row, source: str | None, context: str | None, student_id: str | None
) -> ExternalStudentIdentity | None:
    if any(column is None for column in (source, context, student_id)):
        return None
    values = (_text(row, source), _text(row, context), _text(row, student_id))
    return ExternalStudentIdentity(*values) if all(values) else None  # type: ignore[arg-type]


def _decimal(row: Row, column: str | None, *, required: bool = False) -> Decimal | None:
    if column is None or row.get(column) is None:
        if required:
            raise ValueError("required numeric value is missing")
        return None
    value = row[column]
    if isinstance(value, bool):
        raise ValueError("numeric value is unsafe")
    text = str(value).strip() if isinstance(value, (str, Real, Decimal)) else ""
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("numeric value is invalid") from error
    if not parsed.is_finite():
        raise ValueError("numeric value is not finite")
    return parsed


def _result(row: Row, column: str | None, scale: str | None) -> EvaluationResult:
    """Parse result semantics without changing the source scale."""
    if column is None or row.get(column) is None:
        return EvaluationResult(EvaluationResultStatus.UNKNOWN, scale=scale)
    value = row[column]
    if isinstance(value, bool):
        return EvaluationResult(EvaluationResultStatus.UNKNOWN, str(value), scale=scale)
    if isinstance(value, str):
        if value == '"':
            return EvaluationResult(EvaluationResultStatus.NOT_ATTEMPTED, value, scale=scale)
        text = value.strip()
        if not text:
            return EvaluationResult(EvaluationResultStatus.UNKNOWN, value, scale=scale)
    elif isinstance(value, (Real, Decimal)):
        text = str(value)
    else:
        return EvaluationResult(EvaluationResultStatus.UNKNOWN, str(value), scale=scale)
    try:
        numeric = Decimal(text)
    except InvalidOperation:
        raw_value = value if isinstance(value, str) else text
        return EvaluationResult(EvaluationResultStatus.UNKNOWN, raw_value, scale=scale)
    if not numeric.is_finite():
        return EvaluationResult(
            EvaluationResultStatus.UNKNOWN,
            value if isinstance(value, str) else text,
            scale=scale,
        )
    return EvaluationResult(
        EvaluationResultStatus.ATTEMPTED,
        value if isinstance(value, str) else text,
        numeric,
        scale=scale,
    )


def _timestamp(row: Row, column: str | None) -> datetime | None:
    value = _text(row, column)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp is not ISO-8601") from error


def _raw(row: Row, columns: tuple[str, ...]) -> RawValues:
    """Keep at most eight short scalar values, never a complete row."""
    if len(columns) > 8:
        raise ValueError("at most eight raw columns may be configured")
    result: list[tuple[str, str]] = []
    for column in columns:
        value = row.get(column)
        if isinstance(value, (str, int, float, Decimal)) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                result.append((column, text[:128]))
    return tuple(result)
