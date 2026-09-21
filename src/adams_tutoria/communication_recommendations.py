"""Deterministic, read-only communication recommendations.

This module connects the already computed follow-up and attention contracts.  It
does not persist history, recompute priority, infer evaluation results, or send
messages.
"""

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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
    APPROVED = "approved"
    POSTPONED = "postponed"
    DISCARDED = "discarded"


@dataclass(frozen=True, slots=True)
class RecommendationDiagnostic:
    """Privacy-safe explanation for data that prevented a recommendation."""

    code: str
    message: str
    enrollment_id: UUID | None = None
    edition_id: UUID | None = None
    fields: tuple[str, ...] = ()


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
    closing_within: timedelta = timedelta(days=7)
    progress_below: Decimal | None = None
    recovery_within: timedelta | None = timedelta(days=14)

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for trigger, identifier in self.trigger_mapping.items():
            if not trigger.strip():
                raise ValueError("trigger names must not be blank")
            COMMUNICATION_CATALOG.get(identifier)
            normalized[trigger] = identifier
        object.__setattr__(self, "trigger_mapping", MappingProxyType(normalized))
        if self.closing_within < timedelta(0):
            raise ValueError("closing_within must not be negative")
        if self.progress_below is not None and not Decimal("0") <= self.progress_below <= Decimal(
            "100"
        ):
            raise ValueError("progress_below must be between 0 and 100")
        if self.recovery_within is not None and self.recovery_within < timedelta(0):
            raise ValueError("recovery_within must not be negative")


@dataclass(frozen=True, slots=True)
class EditionPolicyContext:
    """Explicit edition dates and lifecycle state used by temporal policies."""

    edition_id: UUID
    start_date: date | None = None
    end_date: date | None = None
    active: bool | None = True

    def __post_init__(self) -> None:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")

    def remaining(self, as_of: datetime) -> timedelta | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if self.end_date is None:
            return None
        return datetime.combine(self.end_date, datetime.min.time(), tzinfo=UTC) - as_of.astimezone(
            UTC
        )


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
    suggested_at: datetime | None = None
    deduplication_key: str | None = None
    reviewed_at: datetime | None = None
    temporal_context: str | None = None
    remaining: timedelta | None = None

    def discard(self) -> "CommunicationRecommendation":
        return replace(self, status=RecommendationStatus.DISCARDED)

    def approve(self, *, reviewed_at: datetime | None = None) -> "CommunicationRecommendation":
        _validate_optional_aware(reviewed_at, "reviewed_at")
        return replace(self, status=RecommendationStatus.APPROVED, reviewed_at=reviewed_at)

    def review(
        self, status: RecommendationStatus, *, reviewed_at: datetime | None = None
    ) -> "CommunicationRecommendation":
        if status not in (RecommendationStatus.APPROVED, RecommendationStatus.DISCARDED):
            raise ValueError("review status must be approved or discarded")
        _validate_optional_aware(reviewed_at, "reviewed_at")
        return replace(self, status=status, reviewed_at=reviewed_at)

    def postpone(self) -> "CommunicationRecommendation":
        return replace(self, status=RecommendationStatus.POSTPONED)


def _identity(enrollment_id: UUID, edition_id: UUID, identifier: str, trigger: str) -> str:
    value = "\x1f".join((str(enrollment_id), str(edition_id), identifier, trigger))
    return sha256(value.encode("utf-8")).hexdigest()


def _validate_optional_aware(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must be timezone-aware")


def _signals(
    summary: EnrollmentSummary,
    context: EditionPolicyContext | None,
    config: RecommendationConfig,
    as_of: datetime,
) -> tuple[tuple[str, str, str], ...]:
    """Return only explicit semantic signals, never score-derived signals."""

    signals = [
        (reason.code, reason.explanation, f"reason:{reason.code}:{reason.explanation}")
        for reason in summary.follow_up.reasons
    ]
    if summary.evaluations.explicitly_passed:
        signals.append(
            ("passed_evaluation", "Existe un resultado explícito de aprobado.", "evaluation:passed")
        )
    if summary.evaluations.explicitly_failed:
        signals.append(
            (
                "failed_evaluation",
                "Existe un resultado explícito de insuficiente.",
                "evaluation:failed",
            )
        )
    if context is not None and context.end_date is not None:
        remaining = context.end_date - as_of.date()
        if timedelta(0) <= remaining <= config.closing_within:
            signals.append(
                (
                    "closing_soon",
                    "La edición entra en la ventana configurada de cierre.",
                    f"closing:{context.end_date.isoformat()}:{config.closing_within}",
                )
            )
    if (
        config.progress_below is not None
        and summary.progress.percentage is not None
        and summary.progress.percentage < config.progress_below
    ):
        signals.append(
            (
                "insufficient_progress",
                "El progreso disponible está por debajo del umbral configurado.",
                f"progress:{summary.progress.percentage}",
            )
        )
    # Recovery is an independent signal: it must remain evaluable even when
    # the optional low-progress threshold is deliberately disabled.
    if (
        summary.progress.percentage is not None
        and summary.progress.previous_percentage is not None
        and summary.progress.previous_progress_at is not None
        and summary.progress.percentage > summary.progress.previous_percentage
        and (
            config.recovery_within is None
            or as_of - summary.progress.previous_progress_at <= config.recovery_within
        )
    ):
        signals.append(
            (
                "recent_recovery",
                "El progreso observado muestra una mejora respecto a la observación anterior.",
                f"recovery:{summary.progress.previous_progress_at.isoformat()}",
            )
        )
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
    edition_contexts: Mapping[UUID, EditionPolicyContext] | None = None,
    diagnostics: list[RecommendationDiagnostic] | None = None,
) -> tuple[CommunicationRecommendation, ...]:
    """Create isolated, deduplicated recommendations in deterministic order.

    History is consumed only for reads. A missing or ambiguous input produces no
    suggestion and is reported through ``diagnostics`` when supplied. The return
    value remains the approved tuple-of-recommendations contract.
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
            if diagnostics is not None:
                diagnostics.append(
                    RecommendationDiagnostic(
                        "missing_summary",
                        "No hay resumen de matrícula para evaluar la recomendación.",
                        key[0],
                        key[1],
                        ("summary",),
                    )
                )
            continue
        edition_context = None if edition_contexts is None else edition_contexts.get(key[1])
        if (
            edition_context is None
            and "closing_soon" in config.trigger_mapping
            and diagnostics is not None
        ):
            diagnostics.append(
                RecommendationDiagnostic(
                    "missing_edition_context",
                    "Faltan fechas o estado de edición para evaluar reglas temporales.",
                    key[0],
                    key[1],
                    ("edition_context",),
                )
            )
        if (
            summary.progress.percentage is None
            and (
                "insufficient_progress" in config.trigger_mapping
                or "recent_recovery" in config.trigger_mapping
            )
            and diagnostics is not None
        ):
            diagnostics.append(
                RecommendationDiagnostic(
                    "missing_progress",
                    "Falta progreso suficiente para evaluar la regla configurada.",
                    key[0],
                    key[1],
                    ("progress.percentage",),
                )
            )
        elif (
            "recent_recovery" in config.trigger_mapping
            and (
                summary.progress.previous_percentage is None
                or summary.progress.previous_progress_at is None
            )
            and diagnostics is not None
        ):
            diagnostics.append(
                RecommendationDiagnostic(
                    "missing_recovery_baseline",
                    "Falta la observación anterior necesaria para evaluar recuperación.",
                    key[0],
                    key[1],
                    ("progress.previous_percentage", "progress.previous_progress_at"),
                )
            )
        if edition_context is not None and edition_context.active is not True:
            if diagnostics is not None:
                diagnostics.append(
                    RecommendationDiagnostic(
                        "ambiguous_edition_state"
                        if edition_context.active is None
                        else "inactive_edition",
                        "El estado de la edición no permite evaluar recomendaciones.",
                        key[0],
                        key[1],
                        ("active",),
                    )
                )
            continue
        for trigger, explanation, window in _signals(summary, edition_context, config, as_of):
            identifier = config.trigger_mapping.get(trigger)
            if identifier is None:
                continue
            recommendation_id = _identity(*key, identifier, trigger + "\x1f" + window)
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
                    suggested_at=as_of,
                    deduplication_key=recommendation_id,
                    temporal_context=(
                        None if edition_context is None else f"closes:{edition_context.end_date}"
                    ),
                    remaining=(
                        None if edition_context is None else edition_context.remaining(as_of)
                    ),
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
