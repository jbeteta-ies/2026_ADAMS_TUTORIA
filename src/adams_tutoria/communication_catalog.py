"""Immutable catalog of communication types.

The catalog describes communication purposes only.  It does not decide when a
communication should be sent, produce message text, or connect to ADAMS.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class CommunicationType:
    """A stable, data-driven description of one communication purpose."""

    identifier: str
    purpose: str
    conditions: tuple[str, ...]
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class CommunicationCatalog:
    """An immutable ordered collection of communication type definitions."""

    types: tuple[CommunicationType, ...]

    def __post_init__(self) -> None:
        identifiers = tuple(item.identifier for item in self.types)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("communication type identifiers must be unique")
        if any(not identifier.strip() for identifier in identifiers):
            raise ValueError("communication type identifiers must not be blank")

    def get(self, identifier: str) -> CommunicationType:
        """Return a type by its stable identifier."""

        index = _index(self.types)
        try:
            return index[identifier]
        except KeyError:
            raise KeyError(f"unknown communication type: {identifier}") from None

    def with_tones(self, tones: Mapping[str, str]) -> "CommunicationCatalog":
        """Return a catalog with replacement tone metadata.

        Purpose and condition metadata cannot be changed through this method.
        Unknown identifiers are rejected so configuration cannot silently drift.
        """

        index = _index(self.types)
        unknown = set(tones).difference(index)
        if unknown:
            raise ValueError(f"unknown communication type identifiers: {sorted(unknown)}")
        return CommunicationCatalog(
            tuple(replace(item, tone=tones.get(item.identifier, item.tone)) for item in self.types)
        )


def _index(types: Iterable[CommunicationType]) -> Mapping[str, CommunicationType]:
    """Build a read-only lookup from the data in a catalog."""

    return MappingProxyType({item.identifier: item for item in types})


INITIAL_COMMUNICATION_TYPES = (
    CommunicationType(
        identifier="invitation_to_start",
        purpose="Invite an enrolled student to begin the course.",
        conditions=("The student is enrolled.", "The student has not started the course."),
    ),
    CommunicationType(
        identifier="inactivity_reminder",
        purpose="Remind a student who has stopped progressing to resume study.",
        conditions=(
            "The student has started the course.",
            "No qualifying activity exists in the configured inactivity window.",
        ),
    ),
    CommunicationType(
        identifier="pending_evaluation_reminder",
        purpose="Remind a student about an evaluation that remains pending.",
        conditions=(
            "A required evaluation is pending.",
            "The evaluation is available to the student.",
        ),
    ),
    CommunicationType(
        identifier="passed_evaluation_congratulation",
        purpose="Congratulate a student after a passed evaluation.",
        conditions=("A completed evaluation has an explicit passing result.",),
    ),
    CommunicationType(
        identifier="insufficient_result_encouragement",
        purpose="Encourage a student after an insufficient evaluation result.",
        conditions=("A completed evaluation has an explicit insufficient result.",),
    ),
    CommunicationType(
        identifier="completion_congratulation",
        purpose="Congratulate a student after completing the course.",
        conditions=("The course completion condition has been established.",),
    ),
)

COMMUNICATION_CATALOG = CommunicationCatalog(INITIAL_COMMUNICATION_TYPES)
