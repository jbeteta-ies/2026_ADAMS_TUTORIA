"""Deterministic, read-only communication recommendations.

This module connects the already computed follow-up and attention contracts.  It
does not persist history, recompute priority, infer evaluation results, or send
messages.
"""

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from .attention import AttentionCase, PriorityLevel
from .communication_catalog import COMMUNICATION_CATALOG
from .domain import CommunicationStatus
from .message_templates import MessageContext, render_message
from .summary import EnrollmentSummary


class RecommendationStatus(Enum):
    CURRENT = "current"
    POSTPONED = "postponed"
    DISCARDED = "discarded"


@dataclass(frozen=True, slots=True)
class RepetitionPolicy:
    """Limits repeated recommendations without storing or changing history."""

    max_occurrences: int = 1
    cooldown: timedelta = timedelta(0)
    postponed_counts_toward_limit: bool = False

    def __post_init__(self) -> None:
        if self.max_occurrences < 1:
            raise ValueError("max_occurrences must be positive")
        if self.cooldown < timedelta(0):
            raise ValueError("cooldown must not be negative")


@dataclass(frozen=True, slots=True)
class RecommendationConfig:
    """Explicit trigger-to-catalog configuration."""

    trigger_mapping: Mapping[str, str]
    repetition: RepetitionPolicy = RepetitionPolicy()

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for trigger, identifier in self.trigger_mapping.items():
            if not trigger.strip():
                raise ValueError("trigger names must not be blank")
            COMMUNICATION_CATALOG.get(identifier)
            normalized[trigger] = identifier
        object.__setattr__(self, "trigger_mapping", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class RecommendationHistoryEntry:
    """Minimal historical projection accepted by the read-only history port."""

    recommendation_id: str
    enrollment_id: UUID
    edition_id: UUID
    communication_type: str
    occurred_at: datetime
    # ``None`` represents a historical event whose future persistence status is
    # not known.  Keeping that state local avoids pretending that #21's domain
    # status model already exists.
    status: CommunicationStatus | RecommendationStatus | None = None

    def __post_init__(self) -> None:
        if not self.recommendation_id.strip() or not self.communication_type.strip():
            raise ValueError("history identity fields must not be blank")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


class RecommendationHistory(Protocol):
    """Read-only history source; implementations must not be mutated here."""

    def __iter__(self) -> Iterator[RecommendationHistoryEntry]: ...


@dataclass(frozen=True, slots=True)
class CommunicationRecommendation:
    """An immutable suggestion, with priority inherited from ``AttentionCase``."""

    recommendation_id: str
    enrollment_id: UUID
    edition_id: UUID
    communication_type: str
    trigger: str
    reason: str
    priority: PriorityLevel
    status: RecommendationStatus = RecommendationStatus.CURRENT
    rendered_message: str | None = None

    def discard(self) -> "CommunicationRecommendation":
        return replace(self, status=RecommendationStatus.DISCARDED)

    def postpone(self) -> "CommunicationRecommendation":
        return replace(self, status=RecommendationStatus.POSTPONED)


def _identity(enrollment_id: UUID, edition_id: UUID, identifier: str, trigger: str) -> str:
    value = "\x1f".join((str(enrollment_id), str(edition_id), identifier, trigger))
    return sha256(value.encode("utf-8")).hexdigest()


def _signals(summary: EnrollmentSummary) -> tuple[tuple[str, str], ...]:
    """Return only explicit semantic signals, never score-derived signals."""

    signals = [(reason.code, reason.explanation) for reason in summary.follow_up.reasons]
    if summary.evaluations.explicitly_passed:
        signals.append(("passed_evaluation", "Existe un resultado explícito de aprobado."))
    if summary.evaluations.explicitly_failed:
        signals.append(("failed_evaluation", "Existe un resultado explícito de insuficiente."))
    return tuple(signals)


def _index_by_key[T, K](items: Iterable[T], key: Callable[[T], K], label: str) -> dict[K, T]:
    indexed: dict[K, T] = {}
    for item in items:
        item_key = key(item)
        previous = indexed.get(item_key)
        if previous is not None and previous != item:
            raise ValueError(f"conflicting duplicate {label} for key {item_key!r}")
        indexed[item_key] = item
    return indexed


def recommend_communications(
    summaries: Iterable[EnrollmentSummary],
    attention_cases: Iterable[AttentionCase],
    history: RecommendationHistory | Iterable[RecommendationHistoryEntry],
    config: RecommendationConfig,
    *,
    as_of: datetime,
    message_contexts: Mapping[tuple[UUID, UUID], MessageContext] | None = None,
) -> tuple[CommunicationRecommendation, ...]:
    """Create isolated, deduplicated recommendations in deterministic order.

    History is consumed only for reads.  A missing summary or an unmapped signal
    produces no suggestion (insufficient data), rather than a guessed message.
    """

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    summaries_by_key = _index_by_key(
        summaries,
        lambda summary: (summary.enrollment_id, summary.edition_id),
        "summaries",
    )
    cases = _index_by_key(
        attention_cases,
        lambda case: (case.enrollment_id, case.edition_id),
        "attention cases",
    )
    entries: tuple[RecommendationHistoryEntry, ...] = tuple(history)
    result: dict[str, CommunicationRecommendation] = {}
    for key, case in cases.items():
        summary = summaries_by_key.get(key)
        if summary is None:
            continue
        for trigger, explanation in _signals(summary):
            identifier = config.trigger_mapping.get(trigger)
            if identifier is None:
                continue
            recommendation_id = _identity(*key, identifier, trigger)
            matching = [entry for entry in entries if entry.recommendation_id == recommendation_id]
            occurrence_entries = matching
            if not config.repetition.postponed_counts_toward_limit:
                occurrence_entries = [
                    entry
                    for entry in matching
                    if entry.status is not RecommendationStatus.POSTPONED
                ]
            if len(occurrence_entries) >= config.repetition.max_occurrences:
                continue
            if any(
                entry.status not in (CommunicationStatus.DISCARDED, RecommendationStatus.DISCARDED)
                and as_of - entry.occurred_at < config.repetition.cooldown
                for entry in matching
            ):
                continue
            rendered = None
            if message_contexts is not None and key in message_contexts:
                rendered = render_message(identifier, message_contexts[key])
            result.setdefault(
                recommendation_id,
                CommunicationRecommendation(
                    recommendation_id,
                    case.enrollment_id,
                    case.edition_id,
                    identifier,
                    trigger,
                    explanation,
                    case.priority,
                    rendered_message=rendered,
                ),
            )
    priority_order = {
        PriorityLevel.CRITICAL: 0,
        PriorityLevel.HIGH: 1,
        PriorityLevel.MEDIUM: 2,
        PriorityLevel.LOW: 3,
    }
    return tuple(
        sorted(
            result.values(),
            key=lambda item: (
                priority_order[item.priority],
                str(item.edition_id),
                str(item.enrollment_id),
                item.communication_type,
                item.trigger,
                item.recommendation_id,
            ),
        )
    )
