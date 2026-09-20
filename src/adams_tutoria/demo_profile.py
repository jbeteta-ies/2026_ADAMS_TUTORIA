"""Synthetic student profile data for the local dashboard."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from .demo_summary import demo_enrollment_summaries
from .domain import (
    CommunicationRecord,
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationStatus,
    EvaluationTargetType,
    ProgressSnapshot,
    Student,
    TutorAction,
)
from .student_profile import StudentProfile, create_student_profile


def demo_profile(enrollment_id: UUID, actions: tuple[TutorAction, ...] = ()) -> StudentProfile:
    """Return a deterministic, non-operational profile for a demo enrollment."""
    summary = next(
        summary
        for edition_key in (
            "edition-alpha-2026-1",
            "edition-alpha-2026-2",
            "edition-beta-2026-1",
        )
        for summary in demo_enrollment_summaries(edition_key)
        if summary.enrollment_id == enrollment_id
    )
    identity = str(enrollment_id)[-8:]
    student = Student(
        summary.student_id,
        f"Alumno sintético {identity}",
        f"alumno-{identity}@example.invalid",
    )
    course = Course(uuid5(NAMESPACE_URL, "demo-course"), "Curso sintético")
    # Keep the synthetic editions distinct under the catalog's operational
    # identity rules while retaining the human-readable demo label.
    edition = Edition(summary.edition_id, course, "Edición sintética", str(summary.edition_id))
    enrollment = Enrollment(enrollment_id, student, edition)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    snapshots = (
        ProgressSnapshot(
            uuid5(NAMESPACE_URL, f"snapshot:{enrollment_id}"),
            enrollment,
            summary.progress.last_progress_at or now,
            summary.progress.percentage or Decimal("0"),
        ),
    )
    evaluation_count = max(1, summary.evaluations.pending)
    evaluations = tuple(
        Evaluation(
            uuid5(NAMESPACE_URL, f"evaluation:{enrollment_id}:{index}"),
            enrollment,
            EvaluationTargetType.ACTIVITY,
            f"synthetic-{index}",
            status=(
                EvaluationStatus.PENDING
                if index < summary.evaluations.pending
                else EvaluationStatus.COMPLETED
            ),
        )
        for index in range(evaluation_count)
    )
    communications = (
        (
            CommunicationRecord(
                uuid5(NAMESPACE_URL, f"communication:{enrollment_id}"),
                enrollment,
                "inactivity_reminder",
                summary.follow_up.reasons[0].explanation,
                now,
                deduplication_key=f"demo-check-in:{enrollment_id}",
            ),
        )
        if summary.follow_up.reasons
        else ()
    )
    return create_student_profile(
        enrollment,
        summary,
        snapshots,
        evaluations,
        communications,
        actions,
        None,
    )
