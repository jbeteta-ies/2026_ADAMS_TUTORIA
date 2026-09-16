"""Local communication-generation contract with no delivery integration."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from .domain import Enrollment
from .summary import EnrollmentSummary


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

PROMPT_CONTRACT_VERSION = "prompt-context-v1"
NON_INVENTION_RULES = (
    "Usa únicamente los datos del contexto autorizado y la nota del tutor.",
    "No inventes nombres, identificadores, fechas, resultados, progreso ni acciones.",
    "Si falta un dato necesario, indícalo explícitamente y no lo completes.",
    "No reveles ni solicites credenciales, emails, IDs externos, informes crudos u otros alumnos.",
)
_PROMPT_DENYLIST = frozenset(
    PROHIBITED_MODEL_FIELDS
    | {
        "student_id",
        "enrollment_id",
        "edition_id",
        "other_students",
        "internal_notes",
        "notes",
        "credentials",
        "email",
        "external_id",
    }
)


@dataclass(frozen=True, slots=True)
class PromptContext:
    """Small, immutable projection of one enrollment for prompt construction.

    This is deliberately a semantic projection, not a serialization of domain
    objects.  It contains no identity, contact data, raw report, or free-form
    internal note.
    """

    follow_up_reasons: tuple[str, ...] = ()
    progress_percentage: str | None = None
    progress_observed_at: str | None = None
    pending_evaluations: int = 0
    completed_evaluations: int = 0
    recommendation_reason: str | None = None

    def __post_init__(self) -> None:
        if any(not isinstance(item, str) or not item.strip() for item in self.follow_up_reasons):
            raise ValueError("follow_up_reasons must contain non-blank strings")
        for name, value in (
            ("progress_percentage", self.progress_percentage),
            ("progress_observed_at", self.progress_observed_at),
            ("recommendation_reason", self.recommendation_reason),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be blank or a non-blank string")
        if self.pending_evaluations < 0 or self.completed_evaluations < 0:
            raise ValueError("evaluation counts must not be negative")

    @classmethod
    def from_summary(
        cls, summary: EnrollmentSummary, recommendation_reason: str | None = None
    ) -> "PromptContext":
        """Project an existing ``EnrollmentSummary`` without copying its identity."""

        reasons = tuple(reason.code for reason in summary.follow_up.reasons)
        progress = summary.progress
        return cls(
            follow_up_reasons=reasons,
            progress_percentage=None if progress.percentage is None else str(progress.percentage),
            progress_observed_at=None
            if progress.last_progress_at is None
            else progress.last_progress_at.isoformat(),
            pending_evaluations=summary.evaluations.pending,
            completed_evaluations=summary.evaluations.completed,
            recommendation_reason=recommendation_reason,
        )

    def as_mapping(self) -> Mapping[str, Any]:
        values = {
            "follow_up_reasons": self.follow_up_reasons,
            "progress_percentage": self.progress_percentage,
            "progress_observed_at": self.progress_observed_at,
            "pending_evaluations": self.pending_evaluations,
            "completed_evaluations": self.completed_evaluations,
            "recommendation_reason": self.recommendation_reason,
        }
        return MappingProxyType(values)


@dataclass(frozen=True, slots=True)
class PromptRequest:
    """Versioned, local prompt contract; no transport or delivery behavior."""

    context: PromptContext
    communication_type: str
    tone: str
    tutor_text: str | None = None
    version: str = PROMPT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name, value in (("communication_type", self.communication_type), ("tone", self.tone)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-blank string")
        if self.version != PROMPT_CONTRACT_VERSION:
            raise ValueError("unsupported prompt contract version")
        if self.tutor_text is not None:
            if not isinstance(self.tutor_text, str) or len(self.tutor_text) > 2000:
                raise ValueError("tutor_text must be at most 2000 characters")
            lowered = self.tutor_text.casefold()
            if any(term.casefold() in lowered for term in _PROMPT_DENYLIST):
                raise ValueError("tutor_text contains a prohibited field")

    def as_mapping(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "version": self.version,
                "communication_type": self.communication_type,
                "tone": self.tone,
                "context": self.context.as_mapping(),
                "tutor_text": self.tutor_text,
                "rules": NON_INVENTION_RULES,
            }
        )


def serialize_prompt(request: PromptRequest) -> str:
    """Serialize a prompt deterministically for a local model or test fixture."""

    return json.dumps(
        {
            "version": request.version,
            "communication_type": request.communication_type,
            "tone": request.tone,
            "context": dict(request.context.as_mapping()),
            "tutor_text": request.tutor_text,
            "rules": list(NON_INVENTION_RULES),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
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


@dataclass(frozen=True, slots=True)
class DraftGenerationRequest:
    """Explicit input for one attempted draft.

    The enrollment is supplied by the caller; this operation does not select
    recipients or derive a communication recommendation.
    """

    enrollment: Enrollment
    communication_type: str
    reason: str
    prompt: PromptRequest

    def __post_init__(self) -> None:
        for name, value in (
            ("communication_type", self.communication_type),
            ("reason", self.reason),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-blank string")


@dataclass(frozen=True, slots=True)
class DraftGenerationFailure:
    """A failure isolated to one enrollment, without retaining its details."""

    enrollment_id: UUID
    error: str


@dataclass(frozen=True, slots=True)
class DraftGenerationResult:
    records: tuple[GenerationRecord, ...]
    failures: tuple[DraftGenerationFailure, ...]
    duplicate_enrollment_ids: tuple[UUID, ...] = ()


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _plain_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GenerationResponseError("generated draft must be non-empty plain text")
    if len(value) > 16_000:
        raise GenerationResponseError("generated draft exceeds configured limit")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        raise GenerationResponseError("generated draft contains control characters")
    if "<html" in value.casefold() or "<script" in value.casefold():
        raise GenerationResponseError("generated draft must be plain text")
    return value


def _record_context(context: PromptContext) -> dict[str, str]:
    """Store only the legacy record allowlist projection of prompt context."""
    parts = [*context.follow_up_reasons]
    if context.progress_percentage is not None:
        parts.append(f"progress={context.progress_percentage}")
    if context.progress_observed_at is not None:
        parts.append(f"observed_at={context.progress_observed_at}")
    if context.pending_evaluations:
        parts.append(f"pending_evaluations={context.pending_evaluations}")
    if context.completed_evaluations:
        parts.append(f"completed_evaluations={context.completed_evaluations}")
    if context.recommendation_reason is not None:
        parts.append(context.recommendation_reason)
    return {"progress_summary": "; ".join(parts)} if parts else {}


class DraftGenerationService:
    """Generate and persist at most one local draft per enrollment request.

    There is intentionally no fallback: a failed model call produces an
    isolated failure and no record.  This service has no delivery side effect.
    """

    def __init__(
        self,
        generator: GenerationPort,
        repository: "GenerationRepositoryLike",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._generator = generator
        self._repository = repository
        self._clock = clock or (lambda: datetime.now().astimezone())

    def generate(
        self, requests: tuple[DraftGenerationRequest, ...] | list[DraftGenerationRequest]
    ) -> DraftGenerationResult:
        seen: set[UUID] = set()
        records: list[GenerationRecord] = []
        failures: list[DraftGenerationFailure] = []
        duplicates: list[UUID] = []
        for request in requests:
            enrollment_id = request.enrollment.id
            if enrollment_id in seen:
                duplicates.append(enrollment_id)
                continue
            seen.add(enrollment_id)
            try:
                communication_type = _normalize(request.communication_type)
                reason = _normalize(request.reason)
                prompt = PromptRequest(
                    request.prompt.context,
                    communication_type,
                    _normalize(request.prompt.tone),
                    request.prompt.tutor_text,
                    request.prompt.version,
                )
                payload = dict(prompt.as_mapping())
                draft = _plain_text(self._generator.generate(payload))
                record = GenerationRecord.create(
                    request.enrollment,
                    communication_type,
                    reason,
                    draft,
                    self._clock(),
                    _record_context(prompt.context),
                )
                self._repository.save(record)
                records.append(record)
            except Exception as exc:
                failures.append(DraftGenerationFailure(enrollment_id, str(exc)))
        return DraftGenerationResult(tuple(records), tuple(failures), tuple(duplicates))


class GenerationRepositoryLike(Protocol):
    def save(self, value: GenerationRecord) -> None: ...


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
