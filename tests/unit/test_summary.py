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
from adams_tutoria.summary import summarize_edition, summarize_enrollment

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


def test_edition_summary_filters_first_counts_enrollments_and_allows_overlapping_reasons() -> None:
    first = _enrollment()
    second = Enrollment(uuid4(), Student(uuid4(), "Otro sintético"), first.edition)
    other = _enrollment()
    summaries = []
    for enrollment, progress, pending in ((first, "0", 1), (second, "20", 1), (other, "100", 0)):
        evaluations = [
            Evaluation(uuid4(), enrollment, EvaluationTargetType.ACTIVITY, f"a-{index}")
            for index in range(pending)
        ]
        snapshots = [_snapshot(enrollment, progress, AS_OF - timedelta(days=8))]
        follow_up = _assessment(enrollment, snapshots, evaluations)
        summaries.append(
            summarize_enrollment(enrollment, snapshots, evaluations, follow_up, as_of=AS_OF)
        )

    result = summarize_edition(first.edition.id, summaries)

    assert result.total == 2
    assert result.not_started == 1
    assert result.inactive == 1
    assert result.pending_evaluations == 2
    assert result.completed == 0
    assert result.needs_attention == 2


def test_edition_summary_rejects_conflicting_duplicate_enrollment() -> None:
    enrollment = _enrollment()
    summary = summarize_enrollment(enrollment, [], [], _assessment(enrollment, [], []), as_of=AS_OF)
    conflicting = summarize_enrollment(
        enrollment,
        [_snapshot(enrollment, "20", AS_OF)],
        [],
        _assessment(enrollment, [_snapshot(enrollment, "20", AS_OF)], []),
        as_of=AS_OF,
    )

    with pytest.raises(ValueError, match="conflicting summaries"):
        summarize_edition(enrollment.edition.id, [summary, conflicting])


def test_edition_summary_counts_identical_duplicate_once() -> None:
    enrollment = _enrollment()
    summary = summarize_enrollment(
        enrollment,
        [],
        [],
        _assessment(enrollment, [], []),
        as_of=AS_OF,
    )

    result = summarize_edition(enrollment.edition.id, [summary, summary])

    assert result.total == 1
    assert result.not_started == 0
    assert result.inactive == 0
    assert result.pending_evaluations == 0
    assert result.completed == 0
    assert result.needs_attention == 1


def test_edition_summaries_count_same_student_in_both_enrollments() -> None:
    student = Student(uuid4(), "Alumno sintético compartido")
    first_edition = Edition(uuid4(), Course(uuid4(), "Curso sintético"), "Edición uno")
    second_edition = Edition(uuid4(), first_edition.course, "Edición dos")
    first_enrollment = Enrollment(uuid4(), student, first_edition)
    second_enrollment = Enrollment(uuid4(), student, second_edition)

    summaries = [
        summarize_enrollment(
            enrollment,
            [],
            [],
            _assessment(enrollment, [], []),
            as_of=AS_OF,
        )
        for enrollment in (first_enrollment, second_enrollment)
    ]

    first_result = summarize_edition(first_edition.id, summaries)
    second_result = summarize_edition(second_edition.id, summaries)

    assert first_result.total == 1
    assert second_result.total == 1
    assert first_result.total + second_result.total == 2
