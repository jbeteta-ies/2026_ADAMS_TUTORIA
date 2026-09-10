"""Small deterministic demo provider for the dashboard shell.

This is presentation data only. It does not read persistence, imports, or
ADAMS, and contains no personal or operational data.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from .domain import (
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationTargetType,
    ProgressSnapshot,
    Student,
)
from .follow_up import FollowUpRules, assess_follow_up
from .summary import EnrollmentSummary, summarize_enrollment

_AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
_RULES = FollowUpRules(Decimal("0"), timedelta(days=7), Decimal("80"))


def _id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"adams-tutoria-demo:{value}")


def demo_edition_id(edition_key: str) -> UUID:
    """Return the stable synthetic identifier used for a demo edition."""

    return _id(f"edition:{edition_key}")


def demo_enrollment_summaries(edition_key: str) -> tuple[EnrollmentSummary, ...]:
    """Return stable synthetic summaries for one dashboard edition."""

    result: list[EnrollmentSummary] = []
    profiles = {
        "edition-alpha-2026-1": (("0", 1), ("45", 1)),
        "edition-alpha-2026-2": (("90", 0),),
        "edition-beta-2026-1": (("10", 0),),
    }
    for index, (progress, pending) in enumerate(profiles[edition_key]):
        course = Course(_id(f"course:{edition_key}"), "Synthetic course")
        edition = Edition(_id(f"edition:{edition_key}"), course, "Synthetic edition")
        enrollment = Enrollment(
            _id(f"enrollment:{edition_key}:{index}"),
            Student(_id(f"student:{edition_key}:{index}"), "Synthetic record"),
            edition,
        )
        snapshots = [
            # One stable observation is enough for the demo provider.
            ProgressSnapshot(
                _id(f"snapshot:{edition_key}:{index}"),
                enrollment,
                _AS_OF - (timedelta(days=8) if progress == "45" else timedelta(days=1)),
                Decimal(progress),
            )
        ]
        evaluations = [
            Evaluation(
                _id(f"evaluation:{edition_key}:{index}:{evaluation_index}"),
                enrollment,
                EvaluationTargetType.ACTIVITY,
                f"synthetic-{evaluation_index}",
            )
            for evaluation_index in range(pending)
        ]
        follow_up = assess_follow_up(enrollment, snapshots, evaluations, _RULES, as_of=_AS_OF)
        result.append(
            summarize_enrollment(enrollment, snapshots, evaluations, follow_up, as_of=_AS_OF)
        )
    return tuple(result)
