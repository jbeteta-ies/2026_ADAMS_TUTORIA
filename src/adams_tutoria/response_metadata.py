"""Typed, allowlisted metadata for safe navigation response diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from math import isfinite
from re import fullmatch
from typing import Final, TypedDict


class ResponsePhase(StrEnum):
    LOGIN = "login"
    NAVIGATION = "navigation"
    RELOAD = "reload"


class ResponseResult(StrEnum):
    OK = "ok"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


class ExpectedResultMatch(StrEnum):
    YES = "yes"
    NO = "no"
    NOT_CHECKABLE = "not_checkable"


class ResponseMetadataDict(TypedDict):
    step: str
    phase: str
    method: str
    status_code: int | None
    expected_result_match: str
    redirected: bool
    duration: float
    result: str


RESPONSE_METADATA_FIELDS: Final = frozenset(ResponseMetadataDict.__annotations__)
ALLOWED_METHODS: Final = frozenset({"GET", "POST"})
MIN_STATUS_CODE: Final = 100
MAX_STATUS_CODE: Final = 599
MAX_DURATION_SECONDS: Final = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class ResponseMetadata:
    """The only response data that may be persisted in a local log."""

    step: str
    phase: ResponsePhase
    method: str
    status_code: int | None
    expected_result_match: ExpectedResultMatch
    redirected: bool
    duration: float
    result: ResponseResult

    def as_dict(self) -> ResponseMetadataDict:
        value = asdict(self)
        return {
            key: item.value if isinstance(item, StrEnum) else item for key, item in value.items()
        }  # type: ignore[return-value]


def validate_response_metadata(value: ResponseMetadataDict) -> bool:
    """Reject unknown fields and values before a response diagnostic is logged."""
    return (
        set(value) == RESPONSE_METADATA_FIELDS
        and isinstance(value["step"], str)
        and fullmatch(r"step-[1-9][0-9]*", value["step"]) is not None
        and value["phase"] in {item.value for item in ResponsePhase}
        and value["method"] in ALLOWED_METHODS
        and (
            value["status_code"] is None
            or (
                isinstance(value["status_code"], int)
                and not isinstance(value["status_code"], bool)
                and MIN_STATUS_CODE <= value["status_code"] <= MAX_STATUS_CODE
            )
        )
        and value["expected_result_match"] in {item.value for item in ExpectedResultMatch}
        and isinstance(value["redirected"], bool)
        and isinstance(value["duration"], (int, float))
        and not isinstance(value["duration"], bool)
        and isfinite(value["duration"])
        and 0 <= value["duration"] <= MAX_DURATION_SECONDS
        and value["result"] in {item.value for item in ResponseResult}
    )


__all__ = [
    "ExpectedResultMatch",
    "ResponseMetadata",
    "ResponseMetadataDict",
    "ResponsePhase",
    "ResponseResult",
    "validate_response_metadata",
]
