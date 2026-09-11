"""Tests for enrollment-scoped profiles using synthetic records only."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from adams_tutoria.demo_profile import demo_profile
from adams_tutoria.domain import TutorAction
from adams_tutoria.student_profile import create_student_profile


def test_profile_rejects_action_from_another_enrollment() -> None:
    action = TutorAction(uuid4(), uuid4(), datetime(2026, 1, 1, tzinfo=UTC), "Llamar")
    summary = pytest.importorskip("adams_tutoria.demo_summary").demo_enrollment_summaries(
        "edition-alpha-2026-1"
    )[0]
    enrollment = summary.follow_up.enrollment
    with pytest.raises(ValueError, match="tutor actions"):
        create_student_profile(enrollment, summary, (), (), (), (action,), None)


def test_demo_profile_contains_enrollment_scoped_records() -> None:
    summary = pytest.importorskip("adams_tutoria.demo_summary").demo_enrollment_summaries(
        "edition-alpha-2026-1"
    )[0]

    profile = demo_profile(summary.enrollment_id)

    assert profile.snapshots
    assert profile.evaluations
    assert profile.communications
    assert profile.summary.follow_up.reasons
    assert all(snapshot.enrollment.id == summary.enrollment_id for snapshot in profile.snapshots)
    assert all(
        evaluation.enrollment.id == summary.enrollment_id for evaluation in profile.evaluations
    )


def test_demo_profile_beta_without_follow_up_reasons_has_no_suggested_communication() -> None:
    summaries = pytest.importorskip("adams_tutoria.demo_summary").demo_enrollment_summaries(
        "edition-beta-2026-1"
    )
    summary = summaries[0]

    assert summary.follow_up.reasons == ()
    profile = demo_profile(summary.enrollment_id)

    assert profile.communications == ()


def test_demo_profile_renders_persisted_action_projection() -> None:
    summary = pytest.importorskip("adams_tutoria.demo_summary").demo_enrollment_summaries(
        "edition-alpha-2026-1"
    )[0]
    action = TutorAction(
        uuid4(), summary.enrollment_id, datetime(2026, 1, 2, tzinfo=UTC), "Acción persistida"
    )

    profile = demo_profile(summary.enrollment_id, (action,))

    assert profile.actions == (action,)


def test_demo_profile_does_not_invent_tutor_actions() -> None:
    summary = pytest.importorskip("adams_tutoria.demo_summary").demo_enrollment_summaries(
        "edition-alpha-2026-1"
    )[0]

    assert demo_profile(summary.enrollment_id).actions == ()


def test_demo_profiles_distinguish_enrollment_identity() -> None:
    summaries = pytest.importorskip("adams_tutoria.demo_summary").demo_enrollment_summaries(
        "edition-alpha-2026-1"
    )

    first, second = (demo_profile(summary.enrollment_id) for summary in summaries)

    assert first.enrollment.id != second.enrollment.id
    assert first.enrollment.student.id != second.enrollment.student.id
    assert first.enrollment.student.email != second.enrollment.student.email
    assert first.snapshots[0].id != second.snapshots[0].id
