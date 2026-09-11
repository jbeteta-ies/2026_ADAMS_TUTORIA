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
    external_id: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        if not Decimal("0") <= self.progress_percentage <= Decimal("100"):
            raise ValueError("progress_percentage must be between 0 and 100")
        if self.external_id is not None:
            _require_non_blank(self.external_id, "external_id")


class EvaluationTargetType(Enum):
    """The level at which an evaluation is reported."""

    MODULE = "module"
    ACTIVITY = "activity"


class EvaluationStatus(Enum):
    """Lifecycle state reported for an evaluation."""

    PENDING = "pending"
    COMPLETED = "completed"


class CommunicationStatus(Enum):
    """Review and manual-delivery state of a communication record."""

    SUGGESTED = "suggested"
    APPROVED = "approved"
    DISCARDED = "discarded"
    POSTPONED = "postponed"
    COPIED = "copied"
    SENT = "sent"


@dataclass(frozen=True)
class TutorAction:
    """An action recorded by a tutor, linked only to an enrollment."""

    id: UUID
    enrollment_id: UUID
    occurred_at: datetime
    action: str
    note: str = ""

    def __post_init__(self) -> None:
        _require_aware(self.occurred_at, "occurred_at")
        _require_non_blank(self.action, "action")


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
    target_label: str | None = None
    external_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.target_id, "target_id")
        if self.target_label is not None:
            _require_non_blank(self.target_label, "target_label")
        if self.external_id is not None:
            _require_non_blank(self.external_id, "external_id")
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


@dataclass(frozen=True)
class CommunicationRecord:
    """A communication event or proposal associated with an enrollment."""

    id: UUID
    enrollment: Enrollment
    communication_type: str
    reason: str
    suggested_at: datetime
    status: CommunicationStatus = CommunicationStatus.SUGGESTED
    reviewed_at: datetime | None = None
    sent_at: datetime | None = None
    deduplication_key: str = ""
    context_key: str | None = None
    recommendation_id: str | None = None
    trigger: str | None = None
    edition_id: UUID | None = None
    postponed_at: datetime | None = None
    copied_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.communication_type, "communication_type")
        _require_non_blank(self.reason, "reason")
        _require_non_blank(self.deduplication_key, "deduplication_key")
        if self.context_key is not None:
            _require_non_blank(self.context_key, "context_key")
        if self.recommendation_id is not None:
            _require_non_blank(self.recommendation_id, "recommendation_id")
        if self.trigger is not None:
            _require_non_blank(self.trigger, "trigger")
        if self.edition_id is None:
            object.__setattr__(self, "edition_id", self.enrollment.edition.id)

        _require_aware(self.suggested_at, "suggested_at")
        if self.reviewed_at is not None:
            _require_aware(self.reviewed_at, "reviewed_at")
            if self.reviewed_at < self.suggested_at:
                raise ValueError("reviewed_at must not be before suggested_at")
        if self.sent_at is not None:
            _require_aware(self.sent_at, "sent_at")
            if self.reviewed_at is None:
                raise ValueError("sent_at requires reviewed_at")
            if self.sent_at < self.reviewed_at:
                raise ValueError("sent_at must not be before reviewed_at")
            if self.copied_at is not None and self.sent_at < self.copied_at:
                raise ValueError("sent_at must not be before copied_at")
        for field_name, value in (
            ("postponed_at", self.postponed_at),
            ("copied_at", self.copied_at),
        ):
            if value is not None:
                _require_aware(value, field_name)
                if value < self.suggested_at:
                    raise ValueError(f"{field_name} must not be before suggested_at")
        if (
            self.copied_at is not None
            and self.reviewed_at is not None
            and self.copied_at < self.reviewed_at
        ):
            raise ValueError("copied_at must not be before reviewed_at")

        if self.status is CommunicationStatus.SUGGESTED:
            if self.reviewed_at is not None or self.sent_at is not None:
                raise ValueError("suggested communication cannot be reviewed or sent")
        elif self.status in (CommunicationStatus.APPROVED, CommunicationStatus.DISCARDED):
            if self.reviewed_at is None:
                raise ValueError(f"{self.status.value} communication requires reviewed_at")
            if self.sent_at is not None:
                raise ValueError(f"{self.status.value} communication cannot be sent")
        elif self.status is CommunicationStatus.POSTPONED:
            if self.postponed_at is None:
                raise ValueError("postponed communication requires postponed_at")
            if (
                self.reviewed_at is not None
                or self.sent_at is not None
                or self.copied_at is not None
            ):
                raise ValueError("postponed communication cannot be reviewed, copied, or sent")
        elif self.status is CommunicationStatus.COPIED:
            if self.reviewed_at is None or self.copied_at is None:
                raise ValueError("copied communication requires reviewed_at and copied_at")
            if self.sent_at is not None:
                raise ValueError("copied communication cannot be sent")
        elif self.status is CommunicationStatus.SENT and (
            self.reviewed_at is None or self.sent_at is None
        ):
            raise ValueError("sent communication requires reviewed_at and sent_at")
        if (
            self.status
            not in (
                CommunicationStatus.POSTPONED,
                CommunicationStatus.APPROVED,
                CommunicationStatus.DISCARDED,
            )
            and self.postponed_at is not None
        ):
            raise ValueError("postponed_at is only valid before delivery")
        if (
            self.status not in (CommunicationStatus.COPIED, CommunicationStatus.SENT)
            and self.copied_at is not None
        ):
            raise ValueError("copied_at requires copied or sent status")
