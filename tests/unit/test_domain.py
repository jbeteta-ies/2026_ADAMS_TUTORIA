"""Focused tests for the Course and Edition domain entities."""

from dataclasses import FrozenInstanceError, fields
from datetime import date
from uuid import uuid4

import pytest

from adams_tutoria.domain import Course, Edition


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
