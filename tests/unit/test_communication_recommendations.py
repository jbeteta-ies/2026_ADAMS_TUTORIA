"""Synthetic, deterministic tests for communication recommendations."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from adams_tutoria.attention import AttentionCase, PriorityLevel
from adams_tutoria.communication_recommendations import (
    CommunicationRecommendation,
    RecommendationConfig,
    RecommendationHistoryEntry,
    RecommendationStatus,
    RepetitionPolicy,
    recommend_communications,
)
from adams_tutoria.domain import CommunicationStatus, Course, Edition, Enrollment, Student
from adams_tutoria.follow_up import FollowUpAssessment, FollowUpReason
from adams_tutoria.message_templates import MessageContext
from adams_tutoria.summary import EnrollmentSummary, EvaluationSummary, ProgressSummary

AS_OF = datetime(2026, 2, 1, 12, tzinfo=UTC)
EDITION = UUID(int=10)
OTHER_EDITION = UUID(int=11)


def _summary(
    enrollment_id: UUID | None = None,
    edition_id: UUID = EDITION,
    *,
    reasons: tuple[FollowUpReason, ...] = (),
    passed: int = 0,
    failed: int = 0,
) -> EnrollmentSummary:
    enrollment_id = enrollment_id or UUID(int=1)
    edition = Edition(edition_id, Course(UUID(int=20), "Curso sintético"), "Edición sintética")
    enrollment = Enrollment(enrollment_id, Student(UUID(int=30), "Alumno sintético"), edition)
    assessment = FollowUpAssessment(enrollment, AS_OF, reasons)
    return EnrollmentSummary(
        enrollment_id,
        enrollment.student.id,
        edition_id,
        ProgressSummary(None, None),
        EvaluationSummary(passed + failed, 0, passed + failed, passed, failed, 0),
        assessment,
    )


def _case(
    summary: EnrollmentSummary, priority: PriorityLevel = PriorityLevel.HIGH
) -> AttentionCase:
    return AttentionCase(
        summary.enrollment_id,
        summary.edition_id,
        Decimal("5"),
        priority,
        summary.follow_up.reasons,
    )


def _config(
    mapping: dict[str, str] | None = None,
    *,
    max_occurrences: int = 1,
    cooldown: timedelta = timedelta(0),
    postponed_counts_toward_limit: bool = False,
) -> RecommendationConfig:
    return RecommendationConfig(
        mapping
        or {
            "inactive": "inactivity_reminder",
            "not_started": "invitation_to_start",
            "pending_evaluations": "pending_evaluation_reminder",
            "passed_evaluation": "passed_evaluation_congratulation",
            "failed_evaluation": "insufficient_result_encouragement",
        },
        RepetitionPolicy(max_occurrences, cooldown, postponed_counts_toward_limit),
    )


def _recommend(
    summary: EnrollmentSummary,
    *,
    case: AttentionCase | None = None,
    history: tuple[RecommendationHistoryEntry, ...] = (),
    config: RecommendationConfig | None = None,
    contexts: dict[tuple[UUID, UUID], MessageContext] | None = None,
) -> tuple[CommunicationRecommendation, ...]:
    return recommend_communications(
        [summary],
        [case or _case(summary)],
        history,
        config or _config(),
        as_of=AS_OF,
        message_contexts=contexts,
    )


def test_alert_produces_explainable_recommendation() -> None:
    reason = FollowUpReason("inactive", "La última actividad es antigua.", True)
    result = _recommend(_summary(reasons=(reason,)))

    assert len(result) == 1
    assert result[0].communication_type == "inactivity_reminder"
    assert result[0].trigger == "inactive"
    assert result[0].reason == reason.explanation


def test_all_explicit_mappings_are_available_without_score_inference() -> None:
    reasons = (
        FollowUpReason("inactive", "inactivo", True),
        FollowUpReason("not_started", "sin comenzar", True),
        FollowUpReason("pending_evaluations", "pendiente", True),
    )
    result = _recommend(_summary(reasons=reasons, passed=1, failed=1))

    assert {item.communication_type for item in result} == {
        "inactivity_reminder",
        "invitation_to_start",
        "pending_evaluation_reminder",
        "passed_evaluation_congratulation",
        "insufficient_result_encouragement",
    }

    no_explicit_result = _recommend(_summary(reasons=reasons))
    assert {item.trigger for item in no_explicit_result} == {
        "inactive",
        "not_started",
        "pending_evaluations",
    }


def test_no_alert_or_insufficient_data_produces_no_recommendation() -> None:
    no_alert = _summary(reasons=(FollowUpReason("completed", "completo", False),))
    missing_summary = recommend_communications([], [_case(no_alert)], [], _config(), as_of=AS_OF)
    wrong_edition = recommend_communications(
        [_summary(edition_id=OTHER_EDITION, reasons=(FollowUpReason("inactive", "x", True),))],
        [_case(no_alert)],
        [],
        _config(),
        as_of=AS_OF,
    )

    assert _recommend(no_alert) == ()
    assert missing_summary == ()
    assert wrong_edition == ()


@pytest.mark.parametrize(
    ("status", "max_occurrences", "expected"),
    [
        (CommunicationStatus.SUGGESTED, 1, ()),
        (CommunicationStatus.APPROVED, 1, ()),
        (CommunicationStatus.DISCARDED, 2, 1),
        (RecommendationStatus.POSTPONED, 1, 1),
        (CommunicationStatus.SENT, 1, ()),
    ],
)
def test_history_statuses_apply_occurrence_and_cooldown_rules(
    status: CommunicationStatus | RecommendationStatus,
    max_occurrences: int,
    expected: int | tuple[object, ...],
) -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))
    expected_id = _recommend(summary)[0].recommendation_id
    entry = RecommendationHistoryEntry(
        expected_id,
        summary.enrollment_id,
        EDITION,
        "inactivity_reminder",
        AS_OF - timedelta(days=2),
        cast(RecommendationStatus, status),
    )

    result = _recommend(
        summary,
        history=(entry,),
        config=_config(max_occurrences=max_occurrences, cooldown=timedelta(days=2)),
    )
    assert len(result) == expected if isinstance(expected, int) else result == expected


def test_recent_history_uses_cooldown_but_old_history_does_not() -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))
    recommendation_id = _recommend(summary, config=_config(max_occurrences=2))[0].recommendation_id
    recent = RecommendationHistoryEntry(
        recommendation_id,
        summary.enrollment_id,
        EDITION,
        "inactivity_reminder",
        AS_OF - timedelta(hours=1),
    )
    old = RecommendationHistoryEntry(
        recommendation_id,
        summary.enrollment_id,
        EDITION,
        "inactivity_reminder",
        AS_OF - timedelta(days=10),
    )
    config = _config(max_occurrences=2, cooldown=timedelta(days=2))

    assert _recommend(summary, history=(recent,), config=config) == ()
    assert len(_recommend(summary, history=(old,), config=config)) == 1


def test_discarded_history_does_not_trigger_cooldown_but_still_counts() -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))
    recommendation_id = _recommend(summary, config=_config(max_occurrences=2))[0].recommendation_id
    discarded = RecommendationHistoryEntry(
        recommendation_id,
        summary.enrollment_id,
        EDITION,
        "inactivity_reminder",
        AS_OF,
        RecommendationStatus.DISCARDED,
    )

    assert (
        len(
            _recommend(
                summary,
                history=(discarded,),
                config=_config(max_occurrences=2, cooldown=timedelta(days=2)),
            )
        )
        == 1
    )


def test_postponed_history_is_recommendable_after_cooldown() -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))
    recommendation_id = _recommend(summary)[0].recommendation_id
    postponed = RecommendationHistoryEntry(
        recommendation_id,
        summary.enrollment_id,
        EDITION,
        "inactivity_reminder",
        AS_OF - timedelta(days=3),
        RecommendationStatus.POSTPONED,
    )

    result = _recommend(
        summary,
        history=(postponed,),
        config=_config(max_occurrences=1, cooldown=timedelta(days=2)),
    )
    assert len(result) == 1


@pytest.mark.parametrize("postponed_counts_toward_limit", [False, True])
def test_postponed_history_limit_behavior_is_configurable(
    postponed_counts_toward_limit: bool,
) -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))
    recommendation_id = _recommend(summary)[0].recommendation_id
    postponed = RecommendationHistoryEntry(
        recommendation_id,
        summary.enrollment_id,
        EDITION,
        "inactivity_reminder",
        AS_OF - timedelta(days=3),
        RecommendationStatus.POSTPONED,
    )

    result = _recommend(
        summary,
        history=(postponed,),
        config=_config(
            max_occurrences=1,
            cooldown=timedelta(days=2),
            postponed_counts_toward_limit=postponed_counts_toward_limit,
        ),
    )

    assert bool(result) is not postponed_counts_toward_limit


def test_discard_and_postpone_return_new_immutable_values() -> None:
    recommendation = _recommend(_summary(reasons=(FollowUpReason("inactive", "x", True),)))[0]

    discarded = recommendation.discard()
    postponed = recommendation.postpone()
    assert recommendation.status is RecommendationStatus.CURRENT
    assert discarded.status is RecommendationStatus.DISCARDED
    assert postponed.status is RecommendationStatus.POSTPONED
    assert discarded is not recommendation and postponed is not recommendation
    with pytest.raises(FrozenInstanceError):
        recommendation.status = RecommendationStatus.DISCARDED  # type: ignore[misc]


def test_enrollment_and_edition_isolation_and_duplicate_identity() -> None:
    first = _summary(UUID(int=1), EDITION, reasons=(FollowUpReason("inactive", "x", True),))
    other = _summary(UUID(int=2), OTHER_EDITION, reasons=(FollowUpReason("inactive", "y", True),))
    cases = [_case(other), _case(first), _case(first)]

    result = recommend_communications([other, first, first], cases, [], _config(), as_of=AS_OF)
    assert [(item.enrollment_id, item.edition_id) for item in result] == [
        (first.enrollment_id, EDITION),
        (other.enrollment_id, OTHER_EDITION),
    ]


def test_same_student_in_two_editions_uses_each_summary_and_context() -> None:
    first = _summary(UUID(int=1), EDITION, reasons=(FollowUpReason("inactive", "primera", True),))
    second = _summary(
        UUID(int=1), OTHER_EDITION, reasons=(FollowUpReason("inactive", "segunda", True),)
    )
    contexts = {
        (first.enrollment_id, first.edition_id): MessageContext(
            "Alumno sintético", "Curso sintético", "Primera", "contexto 1"
        ),
        (second.enrollment_id, second.edition_id): MessageContext(
            "Alumno sintético", "Curso sintético", "Segunda", "contexto 2"
        ),
    }
    result = recommend_communications(
        [first, second],
        [_case(first), _case(second)],
        [],
        _config(),
        as_of=AS_OF,
        message_contexts=contexts,
    )

    assert [item.reason for item in result] == ["primera", "segunda"]
    assert result[0].rendered_message is not None and "Primera" in result[0].rendered_message
    assert result[1].rendered_message is not None and "Segunda" in result[1].rendered_message


def test_conflicting_duplicate_summary_is_rejected() -> None:
    first = _summary(UUID(int=1), EDITION, reasons=(FollowUpReason("inactive", "a", True),))
    second = _summary(UUID(int=1), EDITION, reasons=(FollowUpReason("inactive", "b", True),))
    with pytest.raises(ValueError, match="conflicting duplicate summaries"):
        recommend_communications([first, second], [_case(first)], [], _config(), as_of=AS_OF)


def test_conflicting_duplicate_case_is_rejected() -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "a", True),))
    with pytest.raises(ValueError, match="conflicting duplicate attention cases"):
        recommend_communications(
            [summary],
            [_case(summary), _case(summary, PriorityLevel.LOW)],
            [],
            _config(),
            as_of=AS_OF,
        )


def test_priority_is_inherited_and_ordering_is_deterministic() -> None:
    low = _summary(UUID(int=1), EDITION, reasons=(FollowUpReason("inactive", "low", True),))
    critical = _summary(
        UUID(int=2), EDITION, reasons=(FollowUpReason("inactive", "critical", True),)
    )
    result = recommend_communications(
        [low, critical],
        [_case(low, PriorityLevel.LOW), _case(critical, PriorityLevel.CRITICAL)],
        [],
        _config(),
        as_of=AS_OF,
    )
    reversed_result = recommend_communications(
        [critical, low],
        [_case(critical, PriorityLevel.CRITICAL), _case(low, PriorityLevel.LOW)],
        [],
        _config(),
        as_of=AS_OF,
    )

    assert [item.priority for item in result] == [PriorityLevel.CRITICAL, PriorityLevel.LOW]
    assert result == reversed_result


def test_policy_configuration_changes_results_without_changing_identity() -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))
    recommendation_id = _recommend(summary)[0].recommendation_id
    history = (
        RecommendationHistoryEntry(
            recommendation_id,
            summary.enrollment_id,
            EDITION,
            "inactivity_reminder",
            AS_OF,
        ),
    )

    assert _recommend(summary, history=history, config=_config(max_occurrences=1)) == ()
    assert _recommend(summary, history=history, config=_config(max_occurrences=2))
    changed = _recommend(summary, config=_config({"inactive": "invitation_to_start"}))
    assert changed[0].recommendation_id != recommendation_id


def test_optional_rendering_is_separate_from_structured_recommendation() -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))
    context = MessageContext("Alumno sintético", "Curso sintético", "Edición sintética", "contexto")
    structured = _recommend(summary)
    rendered = _recommend(summary, contexts={(summary.enrollment_id, summary.edition_id): context})

    assert structured[0].rendered_message is None
    assert rendered[0].rendered_message is not None
    assert "Alumno sintético" in rendered[0].rendered_message
    assert rendered[0].recommendation_id == structured[0].recommendation_id


def test_history_is_read_only_and_no_integration_is_attempted() -> None:
    summary = _summary(reasons=(FollowUpReason("inactive", "x", True),))

    class ReadOnlyHistory(list[RecommendationHistoryEntry]):
        def append(self, item: RecommendationHistoryEntry) -> None:
            raise AssertionError("history must not be written")

        def __setitem__(self, index: object, value: object) -> None:
            raise AssertionError("history must not be written")

    history = ReadOnlyHistory()
    result = _recommend(summary, history=history)  # type: ignore[arg-type]

    assert result
    assert history == []
