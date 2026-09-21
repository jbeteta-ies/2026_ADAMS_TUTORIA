"""Local-only Ollama discovery and validated operational settings.

This module deliberately owns no student data.  It only handles the technical
configuration needed to ask a loopback Ollama service for a draft.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .generation import (
    GenerationConfigurationError,
    GenerationTransportError,
    HttpResponse,
    validate_local_endpoint,
)
from .persistence.database import connection, initialize_database


@dataclass(frozen=True, slots=True)
class OllamaSettings:
    """Allowlisted, non-sensitive local Ollama settings."""

    model: str = ""
    endpoint: str = "http://localhost:11434"
    temperature: float = 0.2
    max_tokens: int = 512
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or len(self.model) > 200:
            raise GenerationConfigurationError("model must be at most 200 characters")
        object.__setattr__(self, "endpoint", validate_local_endpoint(self.endpoint))
        if not 0 <= self.temperature <= 2:
            raise GenerationConfigurationError("temperature must be between 0 and 2")
        if not 1 <= self.max_tokens <= 16_000:
            raise GenerationConfigurationError("max_tokens must be between 1 and 16000")
        if not 0 < self.timeout_seconds <= 300:
            raise GenerationConfigurationError("timeout_seconds must be between 0 and 300")

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "OllamaSettings":
        allowed = {"model", "endpoint", "temperature", "max_tokens", "timeout_seconds"}
        unknown = set(values) - allowed
        if unknown:
            raise GenerationConfigurationError(
                "unknown Ollama settings: " + ", ".join(sorted(unknown))
            )
        try:
            return cls(**values)
        except (TypeError, ValueError) as exc:
            raise GenerationConfigurationError("invalid Ollama settings") from exc

    def as_mapping(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "endpoint": self.endpoint,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
        }


class OllamaSettingsRepository:
    """Persist only the five allowlisted settings in the local SQLite file."""

    def __init__(self, path) -> None:
        self.path = path
        initialize_database(path)

    def get(self) -> OllamaSettings:
        with connection(self.path) as db:
            row = db.execute("SELECT * FROM ollama_settings WHERE id = 1").fetchone()
        if row is None:
            return OllamaSettings()
        return OllamaSettings(
            row["model"],
            row["endpoint"],
            row["temperature"],
            row["max_tokens"],
            row["timeout_seconds"],
        )

    def save(self, settings: OllamaSettings) -> None:
        now = datetime.now(UTC).isoformat()
        with connection(self.path) as db:
            db.execute(
                "INSERT INTO ollama_settings("
                "id,model,endpoint,temperature,max_tokens,timeout_seconds,updated_at) "
                "VALUES(1,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET model=excluded.model, "
                "endpoint=excluded.endpoint, temperature=excluded.temperature, "
                "max_tokens=excluded.max_tokens, "
                "timeout_seconds=excluded.timeout_seconds, updated_at=excluded.updated_at",
                (
                    settings.model,
                    settings.endpoint,
                    settings.temperature,
                    settings.max_tokens,
                    settings.timeout_seconds,
                    now,
                ),
            )


@dataclass(frozen=True, slots=True)
class OllamaModel:
    name: str
    size: int | None = None
    digest: str | None = None


class OllamaDiscoveryTransport(Protocol):
    def get(self, url: str, timeout_seconds: float) -> HttpResponse: ...


class OllamaDiscovery:
    """Safe model discovery through the local ``GET /api/tags`` endpoint."""

    def __init__(self, settings: OllamaSettings, transport: OllamaDiscoveryTransport) -> None:
        self.settings = settings
        self.transport = transport

    def list_models(self) -> tuple[OllamaModel, ...]:
        try:
            response = self.transport.get(
                f"{self.settings.endpoint}/api/tags", self.settings.timeout_seconds
            )
        except Exception as exc:
            raise GenerationTransportError("local model discovery failed") from exc
        if response.status < 200 or response.status >= 300:
            raise GenerationTransportError(f"local model discovery HTTP status {response.status}")
        try:
            decoded = json.loads(response.body)
            raw_models = decoded["models"]
            if not isinstance(raw_models, list):
                raise TypeError
            models = []
            for item in raw_models:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("name"), str)
                    or not item["name"].strip()
                ):
                    raise TypeError
                models.append(OllamaModel(item["name"], item.get("size"), item.get("digest")))
            return tuple(models)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise GenerationTransportError("local model discovery response is invalid") from exc
