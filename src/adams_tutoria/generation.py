"""Local communication-generation contract with no delivery integration."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
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


class GenerationError(Exception):
    """Base error for local generation failures."""


class InvalidEndpointError(GenerationError, ValueError):
    """The configured endpoint is not an allowed local HTTP endpoint."""


class GenerationConfigurationError(GenerationError, ValueError):
    """The local model configuration is invalid."""


class GenerationTransportError(GenerationError):
    """The local model could not be reached or returned an HTTP failure."""


class GenerationResponseError(GenerationError):
    """The local model returned malformed or oversized output."""


class GenerationPort(Protocol):
    """Replaceable application port for generating a draft from a minimized payload."""

    def generate(self, payload: Mapping[str, Any]) -> str: ...


@dataclass(frozen=True)
class OllamaConfig:
    """Safe, local-only Ollama settings; no credentials are accepted."""

    model: str
    endpoint: str = "http://localhost:11434"
    timeout_seconds: float = 30.0
    max_request_bytes: int = 16_384
    max_response_bytes: int = 65_536
    max_output_characters: int = 16_000

    def __post_init__(self) -> None:
        if not self.model.strip() or len(self.model) > 200:
            raise GenerationConfigurationError("model must be non-blank and at most 200 characters")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise GenerationConfigurationError("timeout_seconds must be between 0 and 300")
        if self.max_request_bytes <= 0 or self.max_response_bytes <= 0:
            raise GenerationConfigurationError("request and response limits must be positive")
        if self.max_output_characters <= 0:
            raise GenerationConfigurationError("max_output_characters must be positive")
        object.__setattr__(self, "endpoint", validate_local_endpoint(self.endpoint))


def validate_local_endpoint(endpoint: str) -> str:
    """Validate and return an endpoint restricted to plain HTTP on loopback."""
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise InvalidEndpointError("endpoint is malformed") from exc
    local_names = {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme != "http"
        or hostname not in local_names
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise InvalidEndpointError("endpoint must be plain HTTP on localhost without credentials")
    return endpoint.rstrip("/")


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class HttpTransport(Protocol):
    def post(self, url: str, body: bytes, timeout_seconds: float) -> HttpResponse: ...


class UrllibTransport:
    """Small standard-library transport used only when the adapter is invoked."""

    def post(self, url: str, body: bytes, timeout_seconds: float) -> HttpResponse:
        request = Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return HttpResponse(response.status, response.read())
        except HTTPError as exc:
            raise GenerationTransportError(f"local generation HTTP status {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise GenerationTransportError("local generation transport failed") from exc


class OllamaGenerator:
    """Ollama adapter for the local ``/api/generate`` endpoint."""

    def __init__(self, config: OllamaConfig, transport: HttpTransport | None = None) -> None:
        self.config = config
        self._transport = transport or UrllibTransport()

    def generate(self, payload: Mapping[str, Any]) -> str:
        prompt = payload_json(payload)
        request = {"model": self.config.model, "prompt": prompt, "stream": False}
        body = json.dumps(request, separators=(",", ":")).encode("utf-8")
        if len(body) > self.config.max_request_bytes:
            raise GenerationConfigurationError("generation request exceeds configured limit")
        response = self._transport.post(
            f"{self.config.endpoint}/api/generate", body, self.config.timeout_seconds
        )
        if response.status < 200 or response.status >= 300:
            raise GenerationTransportError(f"local generation HTTP status {response.status}")
        if len(response.body) > self.config.max_response_bytes:
            raise GenerationResponseError("generation response exceeds configured limit")
        try:
            decoded = json.loads(response.body)
            result = decoded["response"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise GenerationResponseError("local generation response is invalid") from exc
        if not isinstance(result, str) or not result.strip():
            raise GenerationResponseError("local generation response has no text")
        if len(result) > self.config.max_output_characters:
            raise GenerationResponseError("generated text exceeds configured limit")
        return result
