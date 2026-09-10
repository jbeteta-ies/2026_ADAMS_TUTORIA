"""Pure preparation helpers for the edition student-tracking table.

The module only projects the existing enrollment summaries and attention cases;
it deliberately does not calculate follow-up or academic rules.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .attention import AttentionCase, PriorityLevel
from .summary import EnrollmentSummary


@dataclass(frozen=True)
class TrackingRow:
    """One table row, identified by an enrollment inside one edition."""

    enrollment_id: UUID
    edition_id: UUID
    student_id: UUID
    status: str
    progress: Decimal | None
    alert: bool
    priority: PriorityLevel | None
    reason: str
    reason_codes: tuple[str, ...]
    last_activity: datetime | None
    pending_evaluations: int


@dataclass(frozen=True)
class TrackingDetail:
    """The selected row and its original, edition-scoped summary."""

    row: TrackingRow
    summary: EnrollmentSummary


_STATUS_ORDER = ("not_started", "inactive", "progress_unknown", "completed", "active")
_PRIORITY_ORDER = {
    PriorityLevel.CRITICAL: 0,
    PriorityLevel.HIGH: 1,
    PriorityLevel.MEDIUM: 2,
    PriorityLevel.LOW: 3,
}


def _status(summary: EnrollmentSummary) -> str:
    codes = {reason.code for reason in summary.follow_up.reasons}
    for candidate in _STATUS_ORDER:
        if candidate in codes:
            return candidate
    return "active"


def prepare_tracking_rows(
    summaries: Iterable[EnrollmentSummary],
    attention_cases: Iterable[AttentionCase],
    edition_id: UUID,
) -> tuple[TrackingRow, ...]:
    """Project summaries for exactly ``edition_id`` into stable table rows."""

    cases = {case.enrollment_id: case for case in attention_cases if case.edition_id == edition_id}
    selected: dict[UUID, EnrollmentSummary] = {}
    for summary in summaries:
        if summary.edition_id != edition_id:
            continue
        previous = selected.get(summary.enrollment_id)
        if previous is not None and previous != summary:
            raise ValueError(f"conflicting summaries for enrollment {summary.enrollment_id}")
        selected[summary.enrollment_id] = summary

    rows: list[TrackingRow] = []
    for summary in selected.values():
        case = cases.get(summary.enrollment_id)
        reason_codes = tuple(reason.code for reason in summary.follow_up.reasons)
        rows.append(
            TrackingRow(
                summary.enrollment_id,
                summary.edition_id,
                summary.student_id,
                _status(summary),
                summary.progress.percentage,
                case is not None,
                None if case is None else case.priority,
                " · ".join(reason.explanation for reason in summary.follow_up.reasons),
                reason_codes,
                summary.last_progress_at,
                summary.evaluations.pending,
            )
        )
    return tuple(sorted(rows, key=lambda row: str(row.enrollment_id)))


def filter_tracking_rows(
    rows: Iterable[TrackingRow],
    *,
    status: str | None = None,
    alert: bool | None = None,
) -> tuple[TrackingRow, ...]:
    """Filter rows without changing their order."""

    return tuple(
        row
        for row in rows
        if (status is None or row.status == status) and (alert is None or row.alert == alert)
    )


def sort_tracking_rows(
    rows: Iterable[TrackingRow],
    *,
    sort_by: str = "priority",
    descending: bool = False,
) -> tuple[TrackingRow, ...]:
    """Sort rows with deterministic enrollment-ID tie-breaking."""

    if sort_by not in {"priority", "status", "progress", "last_activity", "pending_evaluations"}:
        raise ValueError(f"unsupported tracking sort: {sort_by}")

    def key(row: TrackingRow) -> tuple[object, str]:
        if sort_by == "priority":
            value: object = 99 if row.priority is None else _PRIORITY_ORDER[row.priority]
        elif sort_by == "status":
            value = _STATUS_ORDER.index(row.status) if row.status in _STATUS_ORDER else 99
        elif sort_by == "progress":
            value = row.progress is None, row.progress if row.progress is not None else Decimal("0")
        elif sort_by == "last_activity":
            value = row.last_activity is None, row.last_activity or datetime.min
        else:
            value = row.pending_evaluations
        return value, str(row.enrollment_id)

    return tuple(sorted(rows, key=key, reverse=descending))


def select_tracking_detail(
    summaries: Iterable[EnrollmentSummary], rows: Iterable[TrackingRow], enrollment_id: UUID
) -> TrackingDetail | None:
    """Return detail only when the selected enrollment is in the supplied rows."""

    row = next((candidate for candidate in rows if candidate.enrollment_id == enrollment_id), None)
    if row is None:
        return None
    summary = next(
        (
            candidate
            for candidate in summaries
            if candidate.enrollment_id == enrollment_id and candidate.edition_id == row.edition_id
        ),
        None,
    )
    return None if summary is None else TrackingDetail(row, summary)
