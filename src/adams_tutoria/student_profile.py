"""Enrollment-scoped student detail projection."""

from dataclasses import dataclass

from .attention import AttentionCase
from .domain import CommunicationRecord, Enrollment, Evaluation, ProgressSnapshot, TutorAction
from .summary import EnrollmentSummary


@dataclass(frozen=True)
class StudentProfile:
    """Read-only detail view; every operational collection is enrollment-scoped."""

    enrollment: Enrollment
    summary: EnrollmentSummary
    snapshots: tuple[ProgressSnapshot, ...]
    evaluations: tuple[Evaluation, ...]
    communications: tuple[CommunicationRecord, ...]
    actions: tuple[TutorAction, ...]
    attention: AttentionCase | None


def create_student_profile(
    enrollment: Enrollment,
    summary: EnrollmentSummary,
    snapshots: tuple[ProgressSnapshot, ...],
    evaluations: tuple[Evaluation, ...],
    communications: tuple[CommunicationRecord, ...],
    actions: tuple[TutorAction, ...],
    attention: AttentionCase | None,
) -> StudentProfile:
    """Build a profile while rejecting records belonging to another enrollment."""

    enrollment_id = enrollment.id
    if summary.enrollment_id != enrollment_id:
        raise ValueError("summary does not belong to enrollment")
    if any(record.enrollment.id != enrollment_id for record in snapshots):
        raise ValueError("profile records must belong to enrollment")
    if any(record.enrollment.id != enrollment_id for record in evaluations):
        raise ValueError("profile records must belong to enrollment")
    if any(record.enrollment.id != enrollment_id for record in communications):
        raise ValueError("profile records must belong to enrollment")
    if any(record.enrollment_id != enrollment_id for record in actions):
        raise ValueError("tutor actions must belong to enrollment")
    if attention is not None and attention.enrollment_id != enrollment_id:
        raise ValueError("attention case does not belong to enrollment")
    return StudentProfile(
        enrollment, summary, snapshots, evaluations, communications, actions, attention
    )
