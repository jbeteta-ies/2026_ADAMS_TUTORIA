"""Deterministic, explainable attention prioritization.

The public input to this module is deliberately limited to
:class:`~adams_tutoria.summary.EnrollmentSummary`.  It does not recalculate
follow-up rules or inspect their source records.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType
from uuid import UUID

from .follow_up import FollowUpReason
from .summary import EnrollmentSummary


class AttentionConfigurationError(ValueError):
    """Raised when attention weights or thresholds are invalid or incomplete."""


class ConflictingSummaryError(ValueError):
    """Raised when one enrollment is represented by different summaries."""


class PriorityLevel(Enum):
    """Operational urgency, not an academic result."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise AttentionConfigurationError(f"{field} must be a finite decimal") from error
    if not result.is_finite():
        raise AttentionConfigurationError(f"{field} must be a finite decimal")
    return result


@dataclass(frozen=True)
class PriorityThresholds:
    """Minimum scores for each operational priority level."""

    medium: Decimal
    high: Decimal
    critical: Decimal
    low: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        values = {
            "low": _decimal(self.low, "low threshold"),
            "medium": _decimal(self.medium, "medium threshold"),
            "high": _decimal(self.high, "high threshold"),
            "critical": _decimal(self.critical, "critical threshold"),
        }
        if any(value < 0 for value in values.values()):
            raise AttentionConfigurationError("priority thresholds must be non-negative")
        if not values["low"] <= values["medium"] <= values["high"] <= values["critical"]:
            raise AttentionConfigurationError(
                "priority thresholds must be ordered low <= medium <= high <= critical"
            )
        for field, value in values.items():
            object.__setattr__(self, field, value)


@dataclass(frozen=True)
class AttentionConfig:
    """Explicit reason weights and score thresholds for prioritization."""

    reason_weights: Mapping[str, Decimal]
    thresholds: PriorityThresholds

    def __post_init__(self) -> None:
        if not self.reason_weights:
            raise AttentionConfigurationError("reason_weights must not be empty")
        normalized: dict[str, Decimal] = {}
        for code, weight in self.reason_weights.items():
            if not isinstance(code, str) or not code.strip():
                raise AttentionConfigurationError("reason codes must not be blank")
            value = _decimal(weight, f"weight for reason {code!r}")
            if value < 0:
                raise AttentionConfigurationError(
                    f"weight for reason {code!r} must be non-negative"
                )
            normalized[code] = value
        object.__setattr__(self, "reason_weights", MappingProxyType(normalized))


@dataclass(frozen=True)
class AttentionCase:
    """One explainable item in the tutor's attention queue."""

    enrollment_id: UUID
    edition_id: UUID
    score: Decimal
    priority: PriorityLevel
    reasons: tuple[FollowUpReason, ...]


def _priority(score: Decimal, thresholds: PriorityThresholds) -> PriorityLevel:
    if score >= thresholds.critical:
        return PriorityLevel.CRITICAL
    if score >= thresholds.high:
        return PriorityLevel.HIGH
    if score >= thresholds.medium:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW


def _reason_key(reason: FollowUpReason) -> tuple[str, str, bool]:
    return (reason.code, reason.explanation, reason.requires_follow_up)


def prioritize_attention(
    summaries: Iterable[EnrollmentSummary],
    config: AttentionConfig,
    *,
    edition_id: UUID | None = None,
) -> tuple[AttentionCase, ...]:
    """Create a deterministic queue from summaries requiring attention.

    Summaries are deduplicated by enrollment ID. Structurally different
    duplicates fail rather than silently selecting one. Reason objects are
    reused, not reconstructed, so their explanations remain intact.
    """

    unique: dict[UUID, EnrollmentSummary] = {}
    for summary in summaries:
        if edition_id is not None and summary.edition_id != edition_id:
            continue
        previous = unique.get(summary.enrollment_id)
        if previous is not None and previous != summary:
            raise ConflictingSummaryError(
                f"conflicting summaries for enrollment {summary.enrollment_id}"
            )
        unique[summary.enrollment_id] = summary

    cases: list[AttentionCase] = []
    for summary in unique.values():
        if not summary.follow_up.needs_follow_up:
            continue
        unknown = sorted(
            {
                reason.code
                for reason in summary.follow_up.reasons
                if reason.code not in config.reason_weights
            }
        )
        if unknown:
            raise AttentionConfigurationError(
                "missing weights for reason code(s): " + ", ".join(unknown)
            )
        score = sum(
            (
                config.reason_weights[reason.code]
                for reason in summary.follow_up.reasons
                if reason.requires_follow_up
            ),
            Decimal("0"),
        )
        cases.append(
            AttentionCase(
                summary.enrollment_id,
                summary.edition_id,
                score,
                _priority(score, config.thresholds),
                tuple(sorted(summary.follow_up.reasons, key=_reason_key)),
            )
        )

    priority_order = {
        PriorityLevel.CRITICAL: 0,
        PriorityLevel.HIGH: 1,
        PriorityLevel.MEDIUM: 2,
        PriorityLevel.LOW: 3,
    }
    return tuple(
        sorted(
            cases,
            key=lambda case: (
                priority_order[case.priority],
                -case.score,
                str(case.edition_id),
                str(case.enrollment_id),
            ),
        )
    )
