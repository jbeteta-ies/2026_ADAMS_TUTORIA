"""Synthetic tests for the local generation contract."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from adams_tutoria.domain import Course, Edition, Enrollment, Student
from adams_tutoria.generation import (
    GenerationRecord,
    GenerationStatus,
    build_model_payload,
)
from adams_tutoria.persistence.database import initialize_database
from adams_tutoria.persistence.repositories import (
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    GenerationRepository,
    StudentRepository,
)


def _ready(path: Path):
    initialize_database(path)
    course = Course(uuid4(), "Synthetic course", "SYN")
    edition = Edition(uuid4(), course, "Spring", "edition-x", date(2026, 1, 1), date(2026, 6, 1))
    student = Student(uuid4(), "Synthetic Student", "student@example.invalid", "student-x")
    enrollment = Enrollment(uuid4(), student, edition, "enrollment-x")
    CourseRepository(path).save(course)
    EditionRepository(path).save(edition)
    StudentRepository(path).save(student)
    EnrollmentRepository(path).save(enrollment)
    return enrollment


def test_payload_is_allowlisted_and_minimized() -> None:
    payload = build_model_payload(
        "progress_follow_up",
        "low progress",
        {"course_topic": "unit 1"},
    )
    assert payload == {
        "communication_type": "progress_follow_up",
        "reason": "low progress",
        "context": {"course_topic": "unit 1"},
    }


@pytest.mark.parametrize("field", ["student_name", "student_email", "raw_export"])
def test_payload_rejects_prohibited_or_unknown_context_fields(field: str) -> None:
    with pytest.raises(ValueError, match="allowlist"):
        build_model_payload("progress_follow_up", "low progress", {field: "synthetic"})


def test_record_rejects_prohibited_and_outside_allowlist_payload_fields() -> None:
    value = {
        "communication_type": "progress_follow_up",
        "reason": "low progress",
        "student_name": "synthetic",
    }
    with pytest.raises(ValueError, match="allowlist"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            value,
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_record_rejects_prohibited_context_fields() -> None:
    with pytest.raises(ValueError, match="context.*allowlist"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            {
                "communication_type": "progress_follow_up",
                "reason": "low progress",
                "context": {"student_email": "student@example.invalid"},
            },
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_record_rejects_timestamp_before_created_at() -> None:
    with pytest.raises(ValueError, match="edited_at.*created_at"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            {"communication_type": "progress_follow_up", "reason": "low progress"},
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
            GenerationStatus.EDITED,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2025, 12, 31, tzinfo=UTC),
        )


def test_persistence_transitions_manual_sent_and_delete(tmp_path: Path) -> None:
    path = tmp_path / "test.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    repo.transition(
        value.id,
        GenerationStatus.EDITED,
        datetime(2026, 1, 2, tzinfo=UTC),
        "Edited synthetic draft",
    )
    repo.transition(value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 3, tzinfo=UTC))
    repo.transition(value.id, GenerationStatus.COPIED, datetime(2026, 1, 4, tzinfo=UTC))
    repo.transition(value.id, GenerationStatus.SENT, datetime(2026, 1, 5, tzinfo=UTC))
    assert repo.get(value.id).status is GenerationStatus.SENT  # type: ignore[union-attr]
    repo.delete(value.id)
    assert repo.get(value.id) is None


def test_re_review_after_edit_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "re-review.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    repo.transition(value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 2, tzinfo=UTC))
    repo.transition(
        value.id, GenerationStatus.EDITED, datetime(2026, 1, 3, tzinfo=UTC), "Revised draft"
    )
    repo.transition(value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 4, tzinfo=UTC))
    record = repo.get(value.id)
    assert record is not None
    assert record.edited_at == datetime(2026, 1, 3, tzinfo=UTC)
    assert record.reviewed_at == datetime(2026, 1, 4, tzinfo=UTC)


def test_draft_text_is_only_accepted_for_edit_transition(tmp_path: Path) -> None:
    path = tmp_path / "draft-transition.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    with pytest.raises(ValueError, match="draft_text"):
        repo.transition(
            value.id, GenerationStatus.REVIEWED, datetime(2026, 1, 2, tzinfo=UTC), "wrong"
        )


def test_sent_requires_copied_at() -> None:
    with pytest.raises(ValueError, match="SENT requires copied_at"):
        GenerationRecord(
            uuid4(),
            uuid4(),
            "progress_follow_up",
            "low progress",
            {"communication_type": "progress_follow_up", "reason": "low progress"},
            "Synthetic draft",
            datetime(2026, 1, 1, tzinfo=UTC),
            GenerationStatus.SENT,
            sent_at=datetime(2026, 1, 2, tzinfo=UTC),
        )


def test_save_on_conflict_replaces_every_persisted_field(tmp_path: Path) -> None:
    path = tmp_path / "test.sqlite3"
    enrollment = _ready(path)
    second_enrollment = Enrollment(uuid4(), enrollment.student, enrollment.edition, "enrollment-y")
    EnrollmentRepository(path).save(second_enrollment)
    original = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    replacement = replace(
        original,
        enrollment_id=second_enrollment.id,
        communication_type="review_reminder",
        reason="synthetic reason",
        model_payload={"communication_type": "review_reminder", "reason": "synthetic reason"},
        draft_text="Replacement synthetic draft",
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
        status=GenerationStatus.REVIEWED,
        reviewed_at=datetime(2026, 2, 2, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(original)
    repo.save(replacement)
    assert repo.get(original.id) == replacement


@pytest.mark.parametrize(
    ("target", "at"),
    [
        (GenerationStatus.SENT, datetime(2026, 1, 2, tzinfo=UTC)),
        (GenerationStatus.COPIED, datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
def test_invalid_transition_does_not_change_record(
    tmp_path: Path, target: GenerationStatus, at: datetime
) -> None:
    path = tmp_path / "test.sqlite3"
    enrollment = _ready(path)
    value = GenerationRecord.create(
        enrollment,
        "progress_follow_up",
        "low progress",
        "Synthetic draft",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    repo = GenerationRepository(path)
    repo.save(value)
    with pytest.raises(ValueError, match="invalid generation transition"):
        repo.transition(value.id, target, at)
    assert repo.get(value.id) == value
