"""Focused tests for the domain entities."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from adams_tutoria.domain import (
    CommunicationRecord,
    CommunicationStatus,
    ContentSource,
    ContentSourceType,
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationStatus,
    EvaluationTargetType,
    ProgressSnapshot,
    Student,
)


def test_course_stores_identity_and_optional_fields() -> None:
    course_id = uuid4()
    course = Course(course_id, "Synthetic course", "SYN-001", "A test course")

    assert course.id is course_id
    assert course.name == "Synthetic course"
    assert course.code == "SYN-001"
    assert course.description == "A test course"


def test_course_can_reference_a_content_source() -> None:
    source = ContentSource(
        ContentSourceType.REPOSITORY, "https://example.invalid/content", "docs", "v1"
    )
    course = Course(uuid4(), "Synthetic course", content_source=source)
    assert course.content_source is source


@pytest.mark.parametrize("field_name", ["location", "subpath", "revision"])
def test_content_source_rejects_blank_text(field_name: str) -> None:
    values: dict[str, object] = {
        "source_type": ContentSourceType.LOCAL_PATH,
        "location": "synthetic/content",
    }
    values[field_name] = " "
    with pytest.raises(ValueError, match=field_name):
        ContentSource(**values)  # type: ignore[arg-type]


def test_edition_references_course_directly_and_defaults_optionals() -> None:
    course = Course(uuid4(), "Synthetic course")
    edition = Edition(uuid4(), course, "2026 spring")

    assert edition.course is course
    assert edition.external_id is None
    assert edition.start_date is None
    assert edition.end_date is None


def test_edition_supports_multiple_editions_of_one_course() -> None:
    course = Course(uuid4(), "Synthetic course")
    first = Edition(uuid4(), course, "2026 spring")
    second = Edition(uuid4(), course, "2026 autumn")

    assert first.course is second.course is course
    assert first.id != second.id


def test_entities_are_frozen() -> None:
    course = Course(uuid4(), "Synthetic course")

    with pytest.raises(FrozenInstanceError):
        course.name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize("field_name", ["name", "code"])
def test_course_rejects_blank_text(field_name: str) -> None:
    values: dict[str, object] = {"id": uuid4(), "name": "Synthetic course"}
    values[field_name] = "   "

    with pytest.raises(ValueError, match=field_name):
        Course(**values)  # type: ignore[arg-type]


def test_edition_rejects_blank_text_and_reversed_dates() -> None:
    course = Course(uuid4(), "Synthetic course")

    with pytest.raises(ValueError, match="label"):
        Edition(uuid4(), course, "")
    with pytest.raises(ValueError, match="external_id"):
        Edition(uuid4(), course, "2026 spring", external_id=" ")
    with pytest.raises(ValueError, match="end_date"):
        Edition(
            uuid4(),
            course,
            "2026 spring",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 2, 28),
        )


def test_entity_signatures_keep_explicit_uuid_identity_and_optional_defaults() -> None:
    course_fields = fields(Course)
    edition_fields = fields(Edition)

    assert [field.name for field in course_fields] == [
        "id",
        "name",
        "code",
        "description",
        "content_source",
        "active",
    ]
    assert [field.name for field in edition_fields] == [
        "id",
        "course",
        "label",
        "external_id",
        "start_date",
        "end_date",
        "active",
    ]
    assert course_fields[2].default is None
    assert course_fields[3].default is None
    assert course_fields[4].default is None
    assert edition_fields[3].default is None
    assert edition_fields[4].default is None
    assert edition_fields[5].default is None


def test_student_stores_identity_and_optional_fields() -> None:
    student_id = uuid4()
    student = Student(
        student_id,
        "Synthetic Student",
        "student@example.invalid",
        "student-external-001",
    )

    assert student.id is student_id
    assert student.full_name == "Synthetic Student"
    assert student.email == "student@example.invalid"
    assert student.external_id == "student-external-001"


def test_enrollment_references_student_and_edition_directly() -> None:
    course = Course(uuid4(), "Synthetic course")
    edition = Edition(uuid4(), course, "2026 spring")
    student = Student(uuid4(), "Synthetic Student")
    enrollment = Enrollment(uuid4(), student, edition, "enrollment-external-001")

    assert enrollment.student is student
    assert enrollment.edition is edition
    assert enrollment.external_id == "enrollment-external-001"


def test_student_can_be_enrolled_in_multiple_editions_without_duplication() -> None:
    course = Course(uuid4(), "Synthetic course")
    first_edition = Edition(uuid4(), course, "2026 spring")
    second_edition = Edition(uuid4(), course, "2026 autumn")
    student = Student(uuid4(), "Synthetic Student")

    first = Enrollment(uuid4(), student, first_edition)
    second = Enrollment(uuid4(), student, second_edition)

    assert first.student is second.student is student
    assert first.edition is first_edition
    assert second.edition is second_edition
    assert first.id != second.id


@pytest.mark.parametrize("field_name", ["full_name", "email", "external_id"])
def test_student_rejects_blank_text(field_name: str) -> None:
    values: dict[str, object] = {"id": uuid4(), "full_name": "Synthetic Student"}
    values[field_name] = "   "

    with pytest.raises(ValueError, match=field_name):
        Student(**values)  # type: ignore[arg-type]


def test_enrollment_rejects_blank_external_id() -> None:
    student = Student(uuid4(), "Synthetic Student")
    edition = Edition(uuid4(), Course(uuid4(), "Synthetic course"), "2026 spring")

    with pytest.raises(ValueError, match="external_id"):
        Enrollment(uuid4(), student, edition, external_id=" ")


def test_student_and_enrollment_preserve_non_blank_values() -> None:
    student = Student(uuid4(), "  Synthetic Student  ", " student@example.invalid ")
    edition = Edition(uuid4(), Course(uuid4(), "Synthetic course"), "2026 spring")
    enrollment = Enrollment(uuid4(), student, edition, " enrollment-external-001 ")

    assert student.full_name == "  Synthetic Student  "
    assert student.email == " student@example.invalid "
    assert enrollment.external_id == " enrollment-external-001 "


def test_student_and_enrollment_signatures_are_minimal() -> None:
    student_fields = fields(Student)
    enrollment_fields = fields(Enrollment)

    assert [field.name for field in student_fields] == [
        "id",
        "full_name",
        "email",
        "external_id",
    ]
    assert [field.name for field in enrollment_fields] == [
        "id",
        "student",
        "edition",
        "external_id",
    ]
    assert student_fields[2].default is None
    assert student_fields[3].default is None
    assert enrollment_fields[3].default is None


def _enrollment() -> Enrollment:
    return Enrollment(
        uuid4(),
        Student(uuid4(), "Synthetic Student"),
        Edition(uuid4(), Course(uuid4(), "Synthetic course"), "2026 spring"),
    )


def test_progress_snapshots_are_frozen_and_allow_multiple_observations() -> None:
    enrollment = _enrollment()
    first = ProgressSnapshot(uuid4(), enrollment, datetime(2026, 1, 1, tzinfo=UTC), Decimal("0"))
    second = ProgressSnapshot(uuid4(), enrollment, datetime(2026, 1, 8, tzinfo=UTC), Decimal("100"))

    assert first.enrollment is second.enrollment is enrollment
    assert first.progress_percentage == Decimal("0")
    assert first.id != second.id
    with pytest.raises(FrozenInstanceError):
        first.progress_percentage = Decimal("1")  # type: ignore[misc]


@pytest.mark.parametrize("progress", [Decimal("-0.01"), Decimal("100.01")])
def test_progress_percentage_is_inclusive_and_bounded(progress: Decimal) -> None:
    with pytest.raises(ValueError, match="progress_percentage"):
        ProgressSnapshot(uuid4(), _enrollment(), datetime(2026, 1, 1, tzinfo=UTC), progress)


def test_progress_snapshot_rejects_naive_captured_at() -> None:
    with pytest.raises(ValueError, match="captured_at"):
        ProgressSnapshot(uuid4(), _enrollment(), datetime(2026, 1, 1), Decimal("50"))


def test_progress_snapshot_external_id_is_optional_and_preserves_value() -> None:
    enrollment = _enrollment()
    snapshot = ProgressSnapshot(
        uuid4(), enrollment, datetime(2026, 1, 1, tzinfo=UTC), Decimal("50"), "snapshot-x"
    )
    assert snapshot.external_id == "snapshot-x"
    assert (
        ProgressSnapshot(
            uuid4(), enrollment, datetime(2026, 1, 1, tzinfo=UTC), Decimal("50")
        ).external_id
        is None
    )


def test_progress_snapshot_rejects_blank_external_id() -> None:
    with pytest.raises(ValueError, match="external_id"):
        ProgressSnapshot(
            uuid4(), _enrollment(), datetime(2026, 1, 1, tzinfo=UTC), Decimal("50"), " "
        )


def test_evaluation_supports_module_and_activity_targets() -> None:
    enrollment = _enrollment()
    module = Evaluation(uuid4(), enrollment, EvaluationTargetType.MODULE, "synthetic-module-1")
    activity = Evaluation(
        uuid4(), enrollment, EvaluationTargetType.ACTIVITY, "synthetic-activity-1"
    )

    assert module.status is EvaluationStatus.PENDING
    assert activity.target_type is EvaluationTargetType.ACTIVITY


def test_evaluation_score_rules_allow_score_without_max_score() -> None:
    enrollment = _enrollment()
    result = Evaluation(
        uuid4(),
        enrollment,
        EvaluationTargetType.ACTIVITY,
        "synthetic-activity-2",
        EvaluationStatus.COMPLETED,
        score=Decimal("42.5"),
    )

    assert result.score == Decimal("42.5")
    assert result.max_score is None


@pytest.mark.parametrize(
    ("score", "max_score", "message"),
    [(None, Decimal("10"), "max_score"), (Decimal("11"), Decimal("10"), "score")],
)
def test_evaluation_rejects_invalid_score_pairs(
    score: Decimal | None, max_score: Decimal | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Evaluation(
            uuid4(),
            _enrollment(),
            EvaluationTargetType.MODULE,
            "synthetic-module-2",
            EvaluationStatus.COMPLETED,
            score=score,
            max_score=max_score,
        )


def test_pending_evaluation_cannot_have_result_data_or_completion_time() -> None:
    with pytest.raises(ValueError, match="pending"):
        Evaluation(
            uuid4(),
            _enrollment(),
            EvaluationTargetType.MODULE,
            "synthetic-module-3",
            score=Decimal("1"),
        )
    with pytest.raises(ValueError, match="pending"):
        Evaluation(
            uuid4(),
            _enrollment(),
            EvaluationTargetType.MODULE,
            "synthetic-module-4",
            completed_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="pending"):
        Evaluation(
            uuid4(), _enrollment(), EvaluationTargetType.MODULE, "synthetic-module-6", passed=True
        )


def test_completed_evaluation_may_have_no_result_and_never_derives_passed() -> None:
    evaluation = Evaluation(
        uuid4(),
        _enrollment(),
        EvaluationTargetType.MODULE,
        "synthetic-module-5",
        EvaluationStatus.COMPLETED,
    )

    assert evaluation.score is None
    assert evaluation.max_score is None
    assert evaluation.passed is None


def test_completed_evaluation_preserves_explicit_passed_value() -> None:
    evaluation = Evaluation(
        uuid4(),
        _enrollment(),
        EvaluationTargetType.ACTIVITY,
        "synthetic-activity-3",
        EvaluationStatus.COMPLETED,
        score=Decimal("8"),
        max_score=Decimal("10"),
        passed=False,
        completed_at=datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert evaluation.passed is False


def test_evaluation_rejects_naive_completed_at() -> None:
    with pytest.raises(ValueError, match="completed_at"):
        Evaluation(
            uuid4(),
            _enrollment(),
            EvaluationTargetType.MODULE,
            "synthetic-module-7",
            EvaluationStatus.COMPLETED,
            completed_at=datetime(2026, 2, 1),
        )


def test_evaluation_optional_labels_and_external_id_preserve_values_and_none() -> None:
    enrollment = _enrollment()
    evaluation = Evaluation(
        uuid4(),
        enrollment,
        EvaluationTargetType.MODULE,
        "synthetic-module-8",
        target_label="Synthetic module",
        external_id="evaluation-x",
    )
    assert evaluation.target_label == "Synthetic module"
    assert evaluation.external_id == "evaluation-x"
    minimal = Evaluation(uuid4(), enrollment, EvaluationTargetType.MODULE, "synthetic-module-9")
    assert minimal.target_label is None
    assert minimal.external_id is None


@pytest.mark.parametrize("field_name", ["target_label", "external_id"])
def test_evaluation_rejects_blank_optional_text(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        if field_name == "target_label":
            Evaluation(
                uuid4(),
                _enrollment(),
                EvaluationTargetType.MODULE,
                "synthetic-module-10",
                target_label="  ",
            )
        else:
            Evaluation(
                uuid4(),
                _enrollment(),
                EvaluationTargetType.MODULE,
                "synthetic-module-10",
                external_id="  ",
            )


def test_communication_record_stores_enrollment_and_lifecycle_data() -> None:
    enrollment = _enrollment()
    suggested_at = datetime(2026, 3, 1, 10, tzinfo=UTC)
    record = CommunicationRecord(
        uuid4(),
        enrollment,
        "progress.follow_up",
        "progress.below_threshold",
        suggested_at,
        deduplication_key="progress-follow-up:week-10",
        context_key="week-10",
    )

    assert record.enrollment is enrollment
    assert record.status is CommunicationStatus.SUGGESTED
    assert record.deduplication_key == "progress-follow-up:week-10"
    assert record.context_key == "week-10"
    with pytest.raises(FrozenInstanceError):
        record.status = CommunicationStatus.APPROVED  # type: ignore[misc]


def test_communication_record_supports_reviewed_and_sent_states() -> None:
    enrollment = _enrollment()
    suggested_at = datetime(2026, 3, 1, 10, tzinfo=UTC)
    reviewed_at = datetime(2026, 3, 2, 10, tzinfo=UTC)
    sent_at = datetime(2026, 3, 3, 10, tzinfo=UTC)

    approved = CommunicationRecord(
        uuid4(),
        enrollment,
        "check_in",
        "inactivity",
        suggested_at,
        CommunicationStatus.APPROVED,
        reviewed_at,
        None,
        "check-in:1",
    )
    discarded = CommunicationRecord(
        uuid4(),
        enrollment,
        "check_in",
        "inactivity",
        suggested_at,
        CommunicationStatus.DISCARDED,
        reviewed_at,
        None,
        "check-in:2",
    )
    sent = CommunicationRecord(
        uuid4(),
        enrollment,
        "check_in",
        "inactivity",
        suggested_at,
        CommunicationStatus.SENT,
        reviewed_at,
        sent_at,
        "check-in:3",
    )

    assert approved.reviewed_at == discarded.reviewed_at == reviewed_at
    assert sent.sent_at == sent_at


@pytest.mark.parametrize("field_name", ["communication_type", "reason", "deduplication_key"])
def test_communication_record_rejects_blank_required_codes(field_name: str) -> None:
    values: dict[str, object] = {
        "id": uuid4(),
        "enrollment": _enrollment(),
        "communication_type": "check_in",
        "reason": "inactivity",
        "suggested_at": datetime(2026, 3, 1, tzinfo=UTC),
        "deduplication_key": "check-in:1",
    }
    values[field_name] = " "
    with pytest.raises(ValueError, match=field_name):
        CommunicationRecord(**values)  # type: ignore[arg-type]


def test_communication_record_rejects_blank_optional_context_key() -> None:
    with pytest.raises(ValueError, match="context_key"):
        CommunicationRecord(
            uuid4(),
            _enrollment(),
            "check_in",
            "inactivity",
            datetime(2026, 3, 1, tzinfo=UTC),
            deduplication_key="check-in:1",
            context_key=" ",
        )


def test_communication_record_requires_aware_timestamps_and_order() -> None:
    enrollment = _enrollment()
    suggested_at = datetime(2026, 3, 1, tzinfo=UTC)
    reviewed_at = datetime(2026, 3, 2, tzinfo=UTC)
    with pytest.raises(ValueError, match="suggested_at"):
        CommunicationRecord(
            uuid4(),
            enrollment,
            "check_in",
            "inactivity",
            datetime(2026, 3, 1),
            deduplication_key="k",
        )
    with pytest.raises(ValueError, match="reviewed_at"):
        CommunicationRecord(
            uuid4(),
            enrollment,
            "check_in",
            "inactivity",
            suggested_at,
            CommunicationStatus.APPROVED,
            datetime(2026, 2, 28, tzinfo=UTC),
            None,
            "k",
        )
    with pytest.raises(ValueError, match="sent_at"):
        CommunicationRecord(
            uuid4(),
            enrollment,
            "check_in",
            "inactivity",
            suggested_at,
            CommunicationStatus.SENT,
            reviewed_at,
            datetime(2026, 3, 1, tzinfo=UTC),
            "k",
        )


@pytest.mark.parametrize(
    ("status", "reviewed_at", "sent_at"),
    [
        (CommunicationStatus.SUGGESTED, datetime(2026, 3, 2, tzinfo=UTC), None),
        (CommunicationStatus.SUGGESTED, None, datetime(2026, 3, 3, tzinfo=UTC)),
        (CommunicationStatus.APPROVED, None, None),
        (CommunicationStatus.DISCARDED, None, None),
        (
            CommunicationStatus.APPROVED,
            datetime(2026, 3, 2, tzinfo=UTC),
            datetime(2026, 3, 3, tzinfo=UTC),
        ),
        (CommunicationStatus.SENT, None, datetime(2026, 3, 3, tzinfo=UTC)),
        (CommunicationStatus.SENT, datetime(2026, 3, 2, tzinfo=UTC), None),
    ],
)
def test_communication_record_enforces_status_timestamp_rules(
    status: CommunicationStatus, reviewed_at: datetime | None, sent_at: datetime | None
) -> None:
    with pytest.raises(ValueError):
        CommunicationRecord(
            uuid4(),
            _enrollment(),
            "check_in",
            "inactivity",
            datetime(2026, 3, 1, tzinfo=UTC),
            status,
            reviewed_at,
            sent_at,
            "k",
        )


def test_communication_records_may_share_deduplication_keys() -> None:
    enrollment = _enrollment()
    key = "progress-follow-up:week-10"
    first = CommunicationRecord(
        uuid4(),
        enrollment,
        "check_in",
        "inactivity",
        datetime(2026, 3, 1, tzinfo=UTC),
        deduplication_key=key,
    )
    second = CommunicationRecord(
        uuid4(),
        enrollment,
        "check_in",
        "inactivity",
        datetime(2026, 3, 2, tzinfo=UTC),
        deduplication_key=key,
    )
    assert first.deduplication_key == second.deduplication_key
    assert first.id != second.id
