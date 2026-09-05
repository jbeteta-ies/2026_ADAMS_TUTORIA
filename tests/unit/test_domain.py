"""Focused tests for the domain entities."""

from dataclasses import FrozenInstanceError, fields
from datetime import date
from uuid import uuid4

import pytest

from adams_tutoria.domain import Course, Edition, Enrollment, Student


def test_course_stores_identity_and_optional_fields() -> None:
    course_id = uuid4()
    course = Course(course_id, "Synthetic course", "SYN-001", "A test course")

    assert course.id is course_id
    assert course.name == "Synthetic course"
    assert course.code == "SYN-001"
    assert course.description == "A test course"


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

    assert [field.name for field in course_fields] == ["id", "name", "code", "description"]
    assert [field.name for field in edition_fields] == [
        "id",
        "course",
        "label",
        "external_id",
        "start_date",
        "end_date",
    ]
    assert course_fields[2].default is None
    assert course_fields[3].default is None
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
