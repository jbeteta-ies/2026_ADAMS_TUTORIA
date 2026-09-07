"""Source-independent, explainable follow-up assessment rules.

This module deliberately consumes only the internal enrollment, progress and
evaluation values.  It does not know how those values were obtained and never
derives progress from course elements or evaluation scores.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from adams_tutoria.domain import (
    Enrollment,
    Evaluation,
    EvaluationStatus,
    ProgressSnapshot,
)


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class FollowUpRules:
    """Configuration supplied by the caller, not embedded in the evaluator."""

    not_started_max_progress: Decimal
    inactivity_after: timedelta
    completion_min_progress: Decimal
    flag_pending_evaluations: bool = True

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.not_started_max_progress <= Decimal("100"):
            raise ValueError("not_started_max_progress must be between 0 and 100")
        if not Decimal("0") <= self.completion_min_progress <= Decimal("100"):
            raise ValueError("completion_min_progress must be between 0 and 100")
        if self.inactivity_after < timedelta(0):
            raise ValueError("inactivity_after must not be negative")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "FollowUpRules":
        """Build rules from an external, JSON-like configuration mapping.

        ``inactivity_after_hours`` is a representation choice for configuration
        files; the evaluator itself works with a ``timedelta``.  No defaults are
        supplied for thresholds, so an omitted threshold cannot silently change
        behavior. ``flag_pending_evaluations`` defaults to ``True`` when omitted.
        """

        try:
            return cls(
                not_started_max_progress=Decimal(str(values["not_started_max_progress"])),
                inactivity_after=timedelta(
                    hours=float(values["inactivity_after_hours"])  # type: ignore[arg-type]
                ),
                completion_min_progress=Decimal(str(values["completion_min_progress"])),
                flag_pending_evaluations=bool(values.get("flag_pending_evaluations", True)),
            )
        except KeyError as error:
            raise ValueError(f"missing follow-up rule: {error.args[0]}") from error


@dataclass(frozen=True)
class FollowUpReason:
    """A machine-readable reason with an explanation safe for a tutor view."""

    code: str
    explanation: str
    requires_follow_up: bool


@dataclass(frozen=True)
class FollowUpAssessment:
    """Assessment for one enrollment at an explicit point in time."""

    enrollment: Enrollment
    as_of: datetime
    reasons: tuple[FollowUpReason, ...]

    @property
    def needs_follow_up(self) -> bool:
        return any(reason.requires_follow_up for reason in self.reasons)


def assess_follow_up(
    enrollment: Enrollment,
    snapshots: Iterable[ProgressSnapshot],
    evaluations: Iterable[Evaluation],
    rules: FollowUpRules,
    *,
    as_of: datetime,
) -> FollowUpAssessment:
    """Assess an enrollment using its latest available snapshot at ``as_of``.

    Records belonging to another enrollment are ignored.  Missing progress is
    reported as unknown rather than interpreted as zero.  Evaluation scores,
    targets and labels are never used to calculate or interpret progress.
    """

    _require_aware(as_of, "as_of")
    relevant_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.enrollment.id == enrollment.id and snapshot.captured_at <= as_of
    ]
    latest = max(relevant_snapshots, key=lambda snapshot: snapshot.captured_at, default=None)
    relevant_evaluations = [
        evaluation for evaluation in evaluations if evaluation.enrollment.id == enrollment.id
    ]

    reasons: list[FollowUpReason] = []
    if latest is None:
        reasons.append(
            FollowUpReason(
                "progress_unknown",
                "No hay una observación de progreso disponible a la fecha de evaluación.",
                True,
            )
        )
    else:
        progress = latest.progress_percentage
        if progress <= rules.not_started_max_progress:
            reasons.append(
                FollowUpReason(
                    "not_started",
                    f"El progreso observado ({progress}%) no supera el umbral configurado "
                    f"({rules.not_started_max_progress}%).",
                    True,
                )
            )
        elif (
            as_of - latest.captured_at >= rules.inactivity_after
            and progress < rules.completion_min_progress
        ):
            reasons.append(
                FollowUpReason(
                    "inactive",
                    f"La última observación de progreso tiene una antigüedad de "
                    f"{as_of - latest.captured_at}, igual o superior al intervalo configurado.",
                    True,
                )
            )
        if progress >= rules.completion_min_progress:
            reasons.append(
                FollowUpReason(
                    "completed",
                    f"El progreso observado ({progress}%) alcanza el umbral de finalización "
                    f"({rules.completion_min_progress}%).",
                    False,
                )
            )

    pending_count = sum(
        evaluation.status is EvaluationStatus.PENDING for evaluation in relevant_evaluations
    )
    if rules.flag_pending_evaluations and pending_count:
        reasons.append(
            FollowUpReason(
                "pending_evaluations",
                f"Hay {pending_count} evaluación(es) pendiente(s); no se interpreta su puntuación.",
                True,
            )
        )

    return FollowUpAssessment(enrollment, as_of, tuple(reasons))
