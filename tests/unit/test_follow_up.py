"""Synthetic scenarios for source-independent follow-up rules."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

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

AS_OF = datetime(2026, 4, 1, 12, tzinfo=UTC)


def _enrollment() -> Enrollment:
    return Enrollment(
        uuid4(),
        Student(uuid4(), "Alumno sintético"),
        Edition(uuid4(), Course(uuid4(), "Curso sintético"), "Edición de prueba"),
    )


def _rules() -> FollowUpRules:
    return FollowUpRules(Decimal("0"), timedelta(days=7), Decimal("100"))


def _snapshot(enrollment: Enrollment, progress: str, captured_at: datetime) -> ProgressSnapshot:
    return ProgressSnapshot(uuid4(), enrollment, captured_at, Decimal(progress))


def test_not_started_is_explained_without_using_evaluation_scores() -> None:
    enrollment = _enrollment()
    evaluation = Evaluation(
        uuid4(),
        enrollment,
        EvaluationTargetType.ACTIVITY,
        "actividad-sintetica",
        EvaluationStatus.COMPLETED,
        score=Decimal("99"),
    )

    assessment = assess_follow_up(
        enrollment,
        [_snapshot(enrollment, "0", AS_OF - timedelta(days=1))],
        [evaluation],
        _rules(),
        as_of=AS_OF,
    )

    assert [reason.code for reason in assessment.reasons] == ["not_started"]
    assert assessment.reasons[0].requires_follow_up


def test_latest_snapshot_drives_inactivity_and_old_snapshot_is_ignored() -> None:
    enrollment = _enrollment()
    assessment = assess_follow_up(
        enrollment,
        [
            _snapshot(enrollment, "20", AS_OF - timedelta(days=30)),
            _snapshot(enrollment, "40", AS_OF - timedelta(days=2)),
        ],
        [],
        _rules(),
        as_of=AS_OF,
    )

    assert [reason.code for reason in assessment.reasons] == []


def test_latest_snapshot_is_inactive_when_stale_and_below_completion() -> None:
    enrollment = _enrollment()
    assessment = assess_follow_up(
        enrollment,
        [_snapshot(enrollment, "40", AS_OF - timedelta(days=8))],
        [],
        _rules(),
        as_of=AS_OF,
    )

    assert [reason.code for reason in assessment.reasons] == ["inactive"]
    assert assessment.needs_follow_up


def test_inactivity_threshold_is_inclusive() -> None:
    enrollment = _enrollment()
    assessment = assess_follow_up(
        enrollment,
        [_snapshot(enrollment, "40", AS_OF - timedelta(days=7))],
        [],
        _rules(),
        as_of=AS_OF,
    )

    assert [reason.code for reason in assessment.reasons] == ["inactive"]


def test_not_started_takes_precedence_over_inactive() -> None:
    enrollment = _enrollment()
    assessment = assess_follow_up(
        enrollment,
        [_snapshot(enrollment, "0", AS_OF - timedelta(days=8))],
        [],
        _rules(),
        as_of=AS_OF,
    )

    assert [reason.code for reason in assessment.reasons] == ["not_started"]


def test_pending_evaluations_and_completion_are_reported_independently() -> None:
    enrollment = _enrollment()
    pending = Evaluation(uuid4(), enrollment, EvaluationTargetType.MODULE, "tarea-pendiente")
    assessment = assess_follow_up(
        enrollment,
        [_snapshot(enrollment, "100", AS_OF)],
        [pending],
        _rules(),
        as_of=AS_OF,
    )

    assert [reason.code for reason in assessment.reasons] == ["completed", "pending_evaluations"]
    assert assessment.needs_follow_up


def test_missing_progress_is_conservative_and_future_snapshot_is_not_used() -> None:
    enrollment = _enrollment()
    assessment = assess_follow_up(
        enrollment,
        [_snapshot(enrollment, "100", AS_OF + timedelta(minutes=1))],
        [],
        _rules(),
        as_of=AS_OF,
    )

    assert [reason.code for reason in assessment.reasons] == ["progress_unknown"]
    assert assessment.needs_follow_up


def test_rules_can_be_supplied_from_external_mapping() -> None:
    rules = FollowUpRules.from_mapping(
        {
            "not_started_max_progress": "5",
            "inactivity_after_hours": 48,
            "completion_min_progress": "95",
        }
    )
    assert rules.not_started_max_progress == Decimal("5")
    assert rules.inactivity_after == timedelta(hours=48)
    assert rules.flag_pending_evaluations is True


def test_rules_mapping_requires_each_threshold() -> None:
    for missing_key in (
        "not_started_max_progress",
        "inactivity_after_hours",
        "completion_min_progress",
    ):
        values = {
            "not_started_max_progress": "5",
            "inactivity_after_hours": 48,
            "completion_min_progress": "95",
        }
        del values[missing_key]

        try:
            FollowUpRules.from_mapping(values)
        except ValueError as error:
            assert missing_key in str(error)
        else:
            raise AssertionError(f"expected missing-key error for {missing_key}")
