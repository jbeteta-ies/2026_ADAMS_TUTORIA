"""Synthetic tests for attention prioritization."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from adams_tutoria.attention import (
    AttentionConfig,
    AttentionConfigurationError,
    ConflictingSummaryError,
    PriorityLevel,
    PriorityThresholds,
    prioritize_attention,
)
from adams_tutoria.domain import Course, Edition, Enrollment, Student
from adams_tutoria.follow_up import FollowUpAssessment, FollowUpReason
from adams_tutoria.summary import EnrollmentSummary, EvaluationSummary, ProgressSummary


def _summary(
    enrollment_id: UUID | None = None,
    edition_id: UUID | None = None,
    reasons: tuple[FollowUpReason, ...] = (),
) -> EnrollmentSummary:
    enrollment_id = enrollment_id or uuid4()
    edition_id = edition_id or uuid4()
    enrollment = Enrollment(
        enrollment_id,
        Student(uuid4(), "Alumno sintético"),
        Edition(edition_id, Course(uuid4(), "Curso sintético"), "Edición sintética"),
    )
    assessment = FollowUpAssessment(enrollment, datetime(2026, 1, 1, tzinfo=UTC), reasons)
    return EnrollmentSummary(
        enrollment_id,
        enrollment.student.id,
        edition_id,
        ProgressSummary(None, None),
        EvaluationSummary(0, 0, 0, 0, 0, 0),
        assessment,
    )


def _config() -> AttentionConfig:
    return AttentionConfig(
        {"inactive": Decimal("5"), "pending": Decimal("2"), "completed": Decimal("0")},
        PriorityThresholds(medium=Decimal("2"), high=Decimal("5"), critical=Decimal("7")),
    )


def test_scores_priorities_explanations_and_reason_objects_are_preserved() -> None:
    inactive = FollowUpReason("inactive", "Explicación sintética", True)
    completed = FollowUpReason("completed", "No requiere atención", False)
    result = prioritize_attention([_summary(reasons=(completed, inactive))], _config())

    assert result[0].score == Decimal("5")
    assert result[0].priority is PriorityLevel.HIGH
    assert result[0].reasons == (completed, inactive)
    assert result[0].reasons[0] is completed
    assert result[0].reasons[1] is inactive


def test_non_attention_summaries_are_excluded() -> None:
    assert (
        prioritize_attention(
            [_summary(reasons=(FollowUpReason("completed", "ok", False),))], _config()
        )
        == ()
    )


def test_deduplicates_equivalent_summaries_and_rejects_conflicts() -> None:
    enrollment_id = uuid4()
    first = _summary(enrollment_id, reasons=(FollowUpReason("inactive", "x", True),))
    assert len(prioritize_attention([first, first], _config())) == 1

    conflict = _summary(
        enrollment_id, edition_id=first.edition_id, reasons=(FollowUpReason("pending", "y", True),)
    )
    with pytest.raises(ConflictingSummaryError, match="conflicting summaries"):
        prioritize_attention([first, conflict], _config())


def test_filter_by_edition_is_applied_before_deduplication_and_output_is_deterministic() -> None:
    wanted, other = uuid4(), uuid4()
    first = _summary(edition_id=wanted, reasons=(FollowUpReason("pending", "p", True),))
    second = _summary(edition_id=other, reasons=(FollowUpReason("inactive", "i", True),))
    result = prioritize_attention([second, first], _config(), edition_id=wanted)
    assert [case.edition_id for case in result] == [wanted]
    assert prioritize_attention([first, second], _config(), edition_id=wanted) == result


def test_unknown_reason_code_fails_without_an_implicit_weight() -> None:
    summary = _summary(reasons=(FollowUpReason("new_reason", "x", True),))
    with pytest.raises(AttentionConfigurationError, match="new_reason"):
        prioritize_attention([summary], _config())


def test_configuration_rejects_negative_weights_and_unordered_thresholds() -> None:
    with pytest.raises(AttentionConfigurationError, match="non-negative"):
        AttentionConfig(
            {"inactive": Decimal("-1")},
            PriorityThresholds(Decimal("1"), Decimal("2"), Decimal("3")),
        )
    with pytest.raises(AttentionConfigurationError, match="ordered"):
        PriorityThresholds(Decimal("3"), Decimal("2"), Decimal("1"))


def test_ties_are_ordered_by_stable_identifiers() -> None:
    first_id, second_id = UUID(int=1), UUID(int=2)
    edition_id = uuid4()
    summaries = [
        _summary(first_id, edition_id, (FollowUpReason("pending", "p", True),)),
        _summary(second_id, edition_id, (FollowUpReason("pending", "p", True),)),
    ]
    result = prioritize_attention(reversed(summaries), _config())
    assert [case.enrollment_id for case in result] == [first_id, second_id]
