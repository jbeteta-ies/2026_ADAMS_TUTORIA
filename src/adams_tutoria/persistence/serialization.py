"""Lossless scalar conversions used by the repositories."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar
from uuid import UUID

E = TypeVar("E", bound=Enum)


def to_db(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Enum):
        return value.value
    return value


def from_uuid(value: str) -> UUID:
    return UUID(value)


def from_date(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


def from_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def from_decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def from_bool(value: int | None) -> bool | None:
    return None if value is None else bool(value)


def from_enum[E: Enum](enum_type: type[E], value: str) -> E:
    return enum_type(value)
