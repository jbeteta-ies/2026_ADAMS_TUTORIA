"""Synthetic unit tests for the edition-scoped tracking projection."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from adams_tutoria.attention import AttentionCase, PriorityLevel
from adams_tutoria.domain import Course, Edition, Enrollment, Student
from adams_tutoria.follow_up import FollowUpAssessment, FollowUpReason
from adams_tutoria.student_tracking import (
    filter_tracking_rows,
    prepare_tracking_rows,
    select_tracking_detail,
    sort_tracking_rows,
)
from adams_tutoria.summary import EnrollmentSummary, EvaluationSummary, ProgressSummary

AS_OF = datetime(2026, 4, 1, tzinfo=UTC)


def _summary(edition: Edition, progress: str | None, *reasons: str) -> EnrollmentSummary:
    enrollment = Enrollment(uuid4(), Student(uuid4(), "Alumno sintético"), edition)
    follow_up = FollowUpAssessment(
        enrollment,
        AS_OF,
        tuple(FollowUpReason(code, f"Razón {code}", True) for code in reasons),
    )
    return EnrollmentSummary(
        enrollment.id,
        enrollment.student.id,
        edition.id,
        ProgressSummary(None if progress is None else Decimal(progress), None),
        EvaluationSummary(0, 0, 0, 0, 0, 0),
        follow_up,
    )


def _case(summary: EnrollmentSummary, priority: PriorityLevel) -> AttentionCase:
    return AttentionCase(
        summary.enrollment_id, summary.edition_id, Decimal("2"), priority, summary.follow_up.reasons
    )


def test_rows_are_isolated_by_edition_and_keep_same_student_enrollments() -> None:
    course = Course(uuid4(), "Curso sintético")
    first = Edition(uuid4(), course, "Primera")
    second = Edition(uuid4(), course, "Segunda")
    shared_student = Student(uuid4(), "Alumno compartido")
    first_summary = _summary(first, "20", "inactive")
    second_summary = _summary(second, "80", "completed")
    first_summary = EnrollmentSummary(
        first_summary.enrollment_id,
        shared_student.id,
        first.id,
        first_summary.progress,
        first_summary.evaluations,
        first_summary.follow_up,
    )
    second_summary = EnrollmentSummary(
        second_summary.enrollment_id,
        shared_student.id,
        second.id,
        second_summary.progress,
        second_summary.evaluations,
        second_summary.follow_up,
    )

    rows = prepare_tracking_rows(
        (first_summary, second_summary), (_case(first_summary, PriorityLevel.HIGH),), first.id
    )

    assert len(rows) == 1
    assert rows[0].edition_id == first.id
    assert rows[0].student_id == second_summary.student_id
    assert rows[0].enrollment_id != second_summary.enrollment_id


def test_filters_cover_status_alert_and_no_alert() -> None:
    edition = Edition(uuid4(), Course(uuid4(), "Curso sintético"), "Edición")
    alerted = _summary(edition, "10", "inactive")
    calm = _summary(edition, "90", "completed")
    rows = prepare_tracking_rows((alerted, calm), (_case(alerted, PriorityLevel.HIGH),), edition.id)

    assert len(filter_tracking_rows(rows, status="inactive")) == 1
    assert len(filter_tracking_rows(rows, alert=True)) == 1
    assert len(filter_tracking_rows(rows, alert=False)) == 1


def test_sorting_is_ascending_descending_and_tie_breaks_by_enrollment() -> None:
    edition = Edition(uuid4(), Course(uuid4(), "Curso sintético"), "Edición")
    first = _summary(edition, "20", "inactive")
    second = _summary(edition, "40", "inactive")
    rows = prepare_tracking_rows(
        (second, first),
        (_case(first, PriorityLevel.HIGH), _case(second, PriorityLevel.HIGH)),
        edition.id,
    )

    ascending = sort_tracking_rows(rows, sort_by="progress")
    descending = sort_tracking_rows(rows, sort_by="progress", descending=True)
    assert ascending[0].progress == Decimal("20")
    assert descending[0].progress == Decimal("40")
    assert [row.enrollment_id for row in sort_tracking_rows(rows)] == sorted(
        (first.enrollment_id, second.enrollment_id), key=str
    )


def test_missing_progress_is_not_converted_to_zero_and_empty_selection_is_safe() -> None:
    edition = Edition(uuid4(), Course(uuid4(), "Curso sintético"), "Edición")
    summary = _summary(edition, None, "progress_unknown")
    rows = prepare_tracking_rows((summary,), (_case(summary, PriorityLevel.CRITICAL),), edition.id)

    assert rows[0].progress is None
    assert select_tracking_detail((summary,), rows, uuid4()) is None
    detail = select_tracking_detail((summary,), rows, summary.enrollment_id)
    assert detail is not None
    assert detail.summary.edition_id == edition.id
