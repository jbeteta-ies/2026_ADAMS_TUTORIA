"""Tests for the immutable, source-independent communication catalog."""

from dataclasses import FrozenInstanceError

import pytest

from adams_tutoria.communication_catalog import (
    COMMUNICATION_CATALOG,
    INITIAL_COMMUNICATION_TYPES,
    CommunicationCatalog,
    CommunicationType,
)

EXPECTED_IDENTIFIERS = (
    "invitation_to_start",
    "inactivity_reminder",
    "pending_evaluation_reminder",
    "passed_evaluation_congratulation",
    "insufficient_result_encouragement",
    "completion_congratulation",
)


def test_initial_catalog_has_exactly_six_stable_types() -> None:
    assert tuple(item.identifier for item in COMMUNICATION_CATALOG.types) == EXPECTED_IDENTIFIERS
    assert COMMUNICATION_CATALOG.types == INITIAL_COMMUNICATION_TYPES


def test_catalog_types_have_purpose_and_conditions() -> None:
    assert all(item.purpose and item.conditions for item in COMMUNICATION_CATALOG.types)


def test_catalog_and_types_are_immutable() -> None:
    item = COMMUNICATION_CATALOG.get("inactivity_reminder")

    with pytest.raises(FrozenInstanceError):
        item.tone = "formal"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        COMMUNICATION_CATALOG.types = ()  # type: ignore[misc]


def test_tone_configuration_returns_new_catalog_without_changing_definitions() -> None:
    configured = COMMUNICATION_CATALOG.with_tones({"inactivity_reminder": "warm"})

    assert configured is not COMMUNICATION_CATALOG
    assert configured.get("inactivity_reminder").tone == "warm"
    assert COMMUNICATION_CATALOG.get("inactivity_reminder").tone == "neutral"
    assert (
        configured.get("inactivity_reminder").purpose
        == COMMUNICATION_CATALOG.get("inactivity_reminder").purpose
    )


def test_catalog_accepts_new_data_definition_without_central_rules() -> None:
    extension = CommunicationType(
        "synthetic_extension", "A synthetic purpose.", ("A synthetic condition.",)
    )
    extended = CommunicationCatalog(COMMUNICATION_CATALOG.types + (extension,))

    assert extended.get("synthetic_extension") is extension


def test_tone_configuration_rejects_unknown_identifier() -> None:
    with pytest.raises(ValueError, match="unknown"):
        COMMUNICATION_CATALOG.with_tones({"not_a_catalog_type": "warm"})
