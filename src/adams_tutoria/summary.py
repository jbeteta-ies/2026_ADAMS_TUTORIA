"""Pure, immutable summaries for one enrollment at a known point in time."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .domain import Enrollment, Evaluation, EvaluationStatus, ProgressSnapshot
from .follow_up import FollowUpAssessment


@dataclass(frozen=True)
class ProgressSummary:
    """The latest applicable progress observation, if one exists."""

    percentage: Decimal | None
    last_progress_at: datetime | None


@dataclass(frozen=True)
class EvaluationSummary:
    """Counts and explicitly reported outcomes, without applying grading rules."""

    total: int
    pending: int
    completed: int
    explicitly_passed: int
    explicitly_failed: int
    outcome_not_reported: int


@dataclass(frozen=True)
class EnrollmentSummary:
    """A read-only consolidated view scoped to exactly one enrollment."""

    enrollment_id: UUID
    student_id: UUID
    edition_id: UUID
    progress: ProgressSummary
    evaluations: EvaluationSummary
    follow_up: FollowUpAssessment

    @property
    def last_progress_at(self) -> datetime | None:
        """Timestamp of progress, not a login time."""

        return self.progress.last_progress_at


def summarize_enrollment(
    enrollment: Enrollment,
    snapshots: Iterable[ProgressSnapshot],
    evaluations: Iterable[Evaluation],
    follow_up: FollowUpAssessment,
    *,
    as_of: datetime,
) -> EnrollmentSummary:
    """Build a deterministic summary for ``enrollment`` at ``as_of``.

    The caller supplies the existing follow-up assessment; this function does
    not recalculate its rules.
    """

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if follow_up.enrollment.id != enrollment.id or follow_up.as_of != as_of:
        raise ValueError("follow_up must belong to enrollment and use the same as_of")

    relevant_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.enrollment.id == enrollment.id and snapshot.captured_at <= as_of
    ]
    latest = max(relevant_snapshots, key=lambda snapshot: snapshot.captured_at, default=None)
    relevant_evaluations = [
        evaluation for evaluation in evaluations if evaluation.enrollment.id == enrollment.id
    ]
    pending = sum(
        evaluation.status is EvaluationStatus.PENDING for evaluation in relevant_evaluations
    )
    completed = sum(
        evaluation.status is EvaluationStatus.COMPLETED for evaluation in relevant_evaluations
    )
    explicitly_passed = sum(evaluation.passed is True for evaluation in relevant_evaluations)
    explicitly_failed = sum(evaluation.passed is False for evaluation in relevant_evaluations)

    return EnrollmentSummary(
        enrollment.id,
        enrollment.student.id,
        enrollment.edition.id,
        ProgressSummary(
            None if latest is None else latest.progress_percentage,
            None if latest is None else latest.captured_at,
        ),
        EvaluationSummary(
            total=len(relevant_evaluations),
            pending=pending,
            completed=completed,
            explicitly_passed=explicitly_passed,
            explicitly_failed=explicitly_failed,
            outcome_not_reported=len(relevant_evaluations) - explicitly_passed - explicitly_failed,
        ),
        follow_up,
    )
