"""Local communication-generation contract with no delivery integration."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from .domain import Enrollment


class GenerationStatus(Enum):
    GENERATED = "GENERATED"
    REVIEWED = "REVIEWED"
    EDITED = "EDITED"
    COPIED = "COPIED"
    DISCARDED = "DISCARDED"
    SENT = "SENT"


ALLOWED_MODEL_FIELDS = frozenset({"communication_type", "reason", "context"})
ALLOWED_CONTEXT_FIELDS = frozenset({"course_topic", "progress_summary"})
PROHIBITED_MODEL_FIELDS = frozenset(
    {
        "student_name",
        "student_email",
        "student_external_id",
        "enrollment_external_id",
        "adams_credentials",
        "adams_session",
        "raw_report",
        "raw_export",
        "full_database_record",
    }
)


def build_model_payload(
    communication_type: str, reason: str, context: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Build an allowlisted, minimized payload for a future local model."""
    if not communication_type.strip() or not reason.strip():
        raise ValueError("communication_type and reason must not be blank")
    unknown_context = set(context or {}) - ALLOWED_CONTEXT_FIELDS
    if unknown_context:
        raise ValueError("context contains fields outside the allowlist")
    payload: dict[str, Any] = {"communication_type": communication_type, "reason": reason}
    if context:
        payload["context"] = dict(context)
    return payload


@dataclass(frozen=True)
class GenerationRecord:
    """A draft linked to an enrollment; SENT is only a manual external mark."""

    id: UUID
    enrollment_id: UUID
    communication_type: str
    reason: str
    model_payload: dict[str, Any]
    draft_text: str
    created_at: datetime
    status: GenerationStatus = GenerationStatus.GENERATED
    reviewed_at: datetime | None = None
    edited_at: datetime | None = None
    copied_at: datetime | None = None
    sent_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not self.communication_type.strip()
            or not self.reason.strip()
            or not self.draft_text.strip()
        ):
            raise ValueError("communication_type, reason and draft_text must not be blank")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if set(self.model_payload) - ALLOWED_MODEL_FIELDS:
            raise ValueError("model_payload contains fields outside the allowlist")
        if set(self.model_payload) & PROHIBITED_MODEL_FIELDS:
            raise ValueError("model_payload contains prohibited fields")
        context = self.model_payload.get("context")
        if context is not None and (
            not isinstance(context, Mapping)
            or set(context) - ALLOWED_CONTEXT_FIELDS
            or set(context) & PROHIBITED_MODEL_FIELDS
        ):
            raise ValueError("model_payload context contains fields outside the allowlist")
        for name, value in (
            ("reviewed_at", self.reviewed_at),
            ("edited_at", self.edited_at),
            ("copied_at", self.copied_at),
            ("sent_at", self.sent_at),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
            if value is not None and value < self.created_at:
                raise ValueError(f"{name} must not be before created_at")
        if self.status is GenerationStatus.COPIED and self.copied_at is None:
            raise ValueError("COPIED requires copied_at")
        if self.status is GenerationStatus.SENT and self.sent_at is None:
            raise ValueError("SENT requires a manual sent_at timestamp")
        if self.status is GenerationStatus.SENT and self.copied_at is None:
            raise ValueError("SENT requires copied_at")

    @classmethod
    def create(
        cls,
        enrollment: Enrollment,
        communication_type: str,
        reason: str,
        draft_text: str,
        created_at: datetime,
        context: Mapping[str, str] | None = None,
    ) -> "GenerationRecord":
        return cls(
            uuid4(),
            enrollment.id,
            communication_type,
            reason,
            build_model_payload(communication_type, reason, context),
            draft_text,
            created_at,
        )


def payload_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
