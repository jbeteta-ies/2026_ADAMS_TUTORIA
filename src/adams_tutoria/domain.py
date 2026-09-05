"""Core domain entities for reusable courses and their editions."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


@dataclass(frozen=True)
class Course:
    """A reusable course definition that can have multiple editions."""

    id: UUID
    name: str
    code: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.name, "name")
        if self.code is not None:
            _require_non_blank(self.code, "code")


@dataclass(frozen=True)
class Edition:
    """A concrete delivery of a :class:`Course`."""

    id: UUID
    course: Course
    label: str
    external_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.label, "label")
        if self.external_id is not None:
            _require_non_blank(self.external_id, "external_id")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")
