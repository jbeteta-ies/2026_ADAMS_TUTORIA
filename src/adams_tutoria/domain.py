"""Core domain entities for reusable courses and their editions."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class Course:
    """A reusable course definition that can have multiple editions."""

    id: UUID
    name: str
    code: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.name, "name")
        if self.code is not None:
            _require_non_blank(self.code, "code")


@dataclass(frozen=True)
class Edition:
    """A concrete delivery of a :class:`Course`."""

    id: UUID
    course: Course
    label: str
    external_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.label, "label")
        if self.external_id is not None:
            _require_non_blank(self.external_id, "external_id")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")


@dataclass(frozen=True)
class Student:
    """A student's identity, independent of any course edition."""

    id: UUID
    full_name: str
    email: str | None = None
    external_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.full_name, "full_name")
        if self.email is not None:
            _require_non_blank(self.email, "email")
        if self.external_id is not None:
            _require_non_blank(self.external_id, "external_id")


@dataclass(frozen=True)
class Enrollment:
    """A student's membership in one concrete course edition."""

    id: UUID
    student: Student
    edition: Edition
    external_id: str | None = None

    def __post_init__(self) -> None:
        if self.external_id is not None:
            _require_non_blank(self.external_id, "external_id")


@dataclass(frozen=True)
class ProgressSnapshot:
    """One observation of an enrollment's progress as a percentage."""

    id: UUID
    enrollment: Enrollment
    captured_at: datetime
    progress_percentage: Decimal

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        if not Decimal("0") <= self.progress_percentage <= Decimal("100"):
            raise ValueError("progress_percentage must be between 0 and 100")


class EvaluationTargetType(Enum):
    """The level at which an evaluation is reported."""

    MODULE = "module"
    ACTIVITY = "activity"


class EvaluationStatus(Enum):
    """Lifecycle state reported for an evaluation."""

    PENDING = "pending"
    COMPLETED = "completed"


@dataclass(frozen=True)
class Evaluation:
    """An evaluation attached to a module or activity of an enrollment.

    A result is optional because ADAMS may report completion separately from
    result data.  No ``passed`` value is derived: passing rules are external
    to this domain model and are not established by the available reports.
    """

    id: UUID
    enrollment: Enrollment
    target_type: EvaluationTargetType
    target_id: str
    status: EvaluationStatus = EvaluationStatus.PENDING
    score: Decimal | None = None
    max_score: Decimal | None = None
    passed: bool | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.target_id, "target_id")
        if self.max_score is not None and self.score is None:
            raise ValueError("max_score requires score")
        if self.score is not None and self.max_score is not None and self.score > self.max_score:
            raise ValueError("score must not be greater than max_score")
        if self.completed_at is not None:
            _require_aware(self.completed_at, "completed_at")
        if self.status is EvaluationStatus.PENDING and (
            self.score is not None
            or self.max_score is not None
            or self.passed is not None
            or self.completed_at is not None
        ):
            raise ValueError("pending evaluation cannot contain result data")
