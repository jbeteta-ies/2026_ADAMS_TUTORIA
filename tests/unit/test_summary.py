"""Synthetic tests for deterministic enrollment summaries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from adams_tutoria.domain import (
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationStatus,
    EvaluationTargetType,
    ProgressSnapshot,
    Student,
)
from adams_tutoria.follow_up import FollowUpRules, assess_follow_up
from adams_tutoria.summary import summarize_enrollment

AS_OF = datetime(2026, 4, 1, 12, tzinfo=UTC)


def _enrollment(label: str = "Edición sintética") -> Enrollment:
    return Enrollment(
        uuid4(),
        Student(uuid4(), "Alumno sintético"),
        Edition(uuid4(), Course(uuid4(), "Curso sintético"), label),
    )


def _snapshot(enrollment: Enrollment, progress: str, captured_at: datetime) -> ProgressSnapshot:
    return ProgressSnapshot(uuid4(), enrollment, captured_at, Decimal(progress))


def _assessment(
    enrollment: Enrollment, snapshots: list[ProgressSnapshot], evaluations: list[Evaluation]
):
    return assess_follow_up(
        enrollment,
        snapshots,
        evaluations,
        FollowUpRules(Decimal("0"), timedelta(days=7), Decimal("100")),
        as_of=AS_OF,
    )


def test_summary_is_scoped_to_enrollment_and_uses_latest_applicable_snapshot() -> None:
    enrollment = _enrollment()
    other = _enrollment("Otra edición")
    snapshots = [
        _snapshot(enrollment, "20", AS_OF - timedelta(days=3)),
        _snapshot(enrollment, "40", AS_OF - timedelta(days=1)),
        _snapshot(enrollment, "99", AS_OF + timedelta(minutes=1)),
        _snapshot(other, "88", AS_OF),
    ]
    evaluations = [
        Evaluation(uuid4(), enrollment, EvaluationTargetType.ACTIVITY, "a1"),
        Evaluation(
            uuid4(),
            enrollment,
            EvaluationTargetType.MODULE,
            "m1",
            EvaluationStatus.COMPLETED,
            score=Decimal("7"),
            passed=True,
        ),
        Evaluation(uuid4(), other, EvaluationTargetType.ACTIVITY, "other"),
    ]
    follow_up = _assessment(enrollment, snapshots, evaluations)
    summary = summarize_enrollment(enrollment, snapshots, evaluations, follow_up, as_of=AS_OF)

    assert summary.enrollment_id == enrollment.id
    assert summary.student_id == enrollment.student.id
    assert summary.edition_id == enrollment.edition.id
    assert summary.progress.percentage == Decimal("40")
    assert summary.last_progress_at == AS_OF - timedelta(days=1)
    assert summary.evaluations.total == 2
    assert summary.evaluations.pending == 1
    assert summary.evaluations.completed == 1
    assert summary.evaluations.explicitly_passed == 1
    assert summary.evaluations.explicitly_failed == 0
    assert summary.evaluations.outcome_not_reported == 1
    assert summary.follow_up is follow_up


def test_summary_does_not_infer_evaluation_outcome() -> None:
    enrollment = _enrollment()
    evaluation = Evaluation(
        uuid4(),
        enrollment,
        EvaluationTargetType.ACTIVITY,
        "actividad",
        EvaluationStatus.COMPLETED,
        score=Decimal("1"),
        max_score=Decimal("10"),
    )
    follow_up = _assessment(enrollment, [], [evaluation])
    summary = summarize_enrollment(enrollment, [], [evaluation], follow_up, as_of=AS_OF)

    assert summary.evaluations.explicitly_passed == 0
    assert summary.evaluations.explicitly_failed == 0
    assert summary.evaluations.outcome_not_reported == 1


def test_summary_has_unknown_progress_when_no_snapshots_exist() -> None:
    enrollment = _enrollment()
    follow_up = _assessment(enrollment, [], [])

    summary = summarize_enrollment(enrollment, [], [], follow_up, as_of=AS_OF)

    assert summary.progress.percentage is None
    assert summary.last_progress_at is None


def test_summary_requires_matching_aware_as_of_and_existing_follow_up() -> None:
    enrollment = _enrollment()
    follow_up = _assessment(enrollment, [], [])
    other_enrollment = _enrollment("Otra edición")
    mismatched_follow_up = _assessment(other_enrollment, [], [])

    with pytest.raises(ValueError, match="timezone-aware"):
        summarize_enrollment(enrollment, [], [], follow_up, as_of=datetime(2026, 4, 1, 12))
    with pytest.raises(ValueError, match="belong to enrollment"):
        summarize_enrollment(enrollment, [], [], mismatched_follow_up, as_of=AS_OF)
    with pytest.raises(ValueError, match="same as_of"):
        summarize_enrollment(enrollment, [], [], follow_up, as_of=AS_OF + timedelta(minutes=1))
