"""Synthetic tests for the persisted communication history."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from test_persistence import _ready

from adams_tutoria.communication_recommendations import RecommendationStatus
from adams_tutoria.domain import CommunicationRecord, CommunicationStatus
from adams_tutoria.persistence.database import connection, initialize_database
from adams_tutoria.persistence.repositories import (
    CommunicationHistoryAdapter,
    CommunicationRecordRepository,
)


def _record(path: Path) -> tuple[CommunicationRecordRepository, CommunicationRecord]:
    _, edition, _, enrollment = _ready(path)
    value = CommunicationRecord(
        uuid4(),
        enrollment,
        "check_in",
        "inactive",
        datetime(2026, 1, 1, tzinfo=UTC),
        deduplication_key="synthetic-key",
        recommendation_id="recommendation-x",
        trigger="inactive",
        edition_id=edition.id,
    )
    repo = CommunicationRecordRepository(path)
    repo.save(value)
    return repo, value


def test_additive_schema_preserves_legacy_ten_column_table(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with connection(path) as db:
        db.execute(
            """CREATE TABLE communication_record (
                id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL,
                communication_type TEXT NOT NULL, reason TEXT NOT NULL, suggested_at TEXT NOT NULL,
                status TEXT NOT NULL, reviewed_at TEXT, sent_at TEXT,
                deduplication_key TEXT NOT NULL, context_key TEXT
            )"""
        )
    initialize_database(path)
    with connection(path) as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(communication_record)")}
    assert {"recommendation_id", "trigger", "edition_id", "postponed_at", "copied_at"} <= columns


def test_transitions_are_explicit_and_round_trip(tmp_path: Path) -> None:
    repo, value = _record(tmp_path / "history.sqlite3")
    repo.transition(value.id, CommunicationStatus.APPROVED, datetime(2026, 1, 2, tzinfo=UTC))
    repo.transition(value.id, CommunicationStatus.COPIED, datetime(2026, 1, 3, tzinfo=UTC))
    repo.transition(value.id, CommunicationStatus.SENT, datetime(2026, 1, 4, tzinfo=UTC))
    assert repo.get(value.id).status is CommunicationStatus.SENT  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="invalid communication transition"):
        repo.transition(value.id, CommunicationStatus.APPROVED, datetime(2026, 1, 5, tzinfo=UTC))


@pytest.mark.parametrize(
    "final_status", [CommunicationStatus.DISCARDED, CommunicationStatus.POSTPONED]
)
def test_suggested_review_transitions_record_reviewed_at(
    tmp_path: Path, final_status: CommunicationStatus
) -> None:
    repo, value = _record(tmp_path / f"{final_status.value}.sqlite3")
    when = datetime(2026, 1, 2, tzinfo=UTC)
    repo.transition(value.id, final_status, when)
    saved = repo.get(value.id)
    assert saved is not None
    if final_status is CommunicationStatus.DISCARDED:
        assert saved.reviewed_at == when
    else:
        assert saved.reviewed_at is None
    if final_status is CommunicationStatus.POSTPONED:
        assert saved.postponed_at == when


@pytest.mark.parametrize(
    "final_status", [CommunicationStatus.APPROVED, CommunicationStatus.DISCARDED]
)
def test_postponed_timestamp_is_preserved_when_resolved(
    tmp_path: Path, final_status: CommunicationStatus
) -> None:
    repo, value = _record(tmp_path / f"resolve-{final_status.value}.sqlite3")
    postponed = datetime(2026, 1, 2, tzinfo=UTC)
    resolved = datetime(2026, 1, 3, tzinfo=UTC)
    repo.transition(value.id, CommunicationStatus.POSTPONED, postponed)
    repo.transition(value.id, final_status, resolved)
    saved = repo.get(value.id)
    assert saved is not None
    assert saved.postponed_at == postponed
    assert saved.reviewed_at == resolved


def test_postponed_delivery_clears_postponed_at_and_preserves_delivery_times(
    tmp_path: Path,
) -> None:
    repo, value = _record(tmp_path / "postponed-delivery.sqlite3")
    postponed = datetime(2026, 1, 2, tzinfo=UTC)
    approved = datetime(2026, 1, 3, tzinfo=UTC)
    copied = datetime(2026, 1, 4, tzinfo=UTC)
    sent = datetime(2026, 1, 5, tzinfo=UTC)

    repo.transition(value.id, CommunicationStatus.POSTPONED, postponed)
    repo.transition(value.id, CommunicationStatus.APPROVED, approved)
    resolved = repo.get(value.id)
    assert resolved is not None
    assert resolved.postponed_at == postponed
    assert resolved.reviewed_at == approved

    repo.transition(value.id, CommunicationStatus.COPIED, copied)
    copied_record = repo.get(value.id)
    assert copied_record is not None
    assert copied_record.postponed_at is None
    assert copied_record.copied_at == copied
    assert copied_record.sent_at is None

    repo.transition(value.id, CommunicationStatus.SENT, sent)
    sent_record = repo.get(value.id)
    assert sent_record is not None
    assert sent_record.postponed_at is None
    assert sent_record.copied_at == copied
    assert sent_record.sent_at == sent


def test_direct_sent_does_not_fabricate_copy_time(tmp_path: Path) -> None:
    repo, value = _record(tmp_path / "direct-sent.sqlite3")
    repo.transition(value.id, CommunicationStatus.APPROVED, datetime(2026, 1, 2, tzinfo=UTC))
    repo.transition(value.id, CommunicationStatus.SENT, datetime(2026, 1, 3, tzinfo=UTC))
    saved = repo.get(value.id)
    assert saved is not None
    assert saved.copied_at is None
    assert saved.sent_at == datetime(2026, 1, 3, tzinfo=UTC)


def test_transition_chronology_is_enforced(tmp_path: Path) -> None:
    repo, value = _record(tmp_path / "chronology.sqlite3")
    with pytest.raises(ValueError, match="not be before suggested_at"):
        repo.transition(value.id, CommunicationStatus.APPROVED, datetime(2025, 12, 31, tzinfo=UTC))
    repo.transition(value.id, CommunicationStatus.APPROVED, datetime(2026, 1, 2, tzinfo=UTC))
    with pytest.raises(ValueError, match="not be before"):
        repo.transition(value.id, CommunicationStatus.COPIED, datetime(2026, 1, 1, tzinfo=UTC))
    repo.transition(value.id, CommunicationStatus.COPIED, datetime(2026, 1, 3, tzinfo=UTC))
    with pytest.raises(ValueError, match="not be before"):
        repo.transition(value.id, CommunicationStatus.SENT, datetime(2026, 1, 2, tzinfo=UTC))


def test_history_adapter_is_filtered_and_does_not_expose_message_text(tmp_path: Path) -> None:
    repo, value = _record(tmp_path / "adapter.sqlite3")
    entries = tuple(CommunicationHistoryAdapter(repo, value.enrollment.id, value.edition_id))
    assert len(entries) == 1
    assert entries[0].recommendation_id == "recommendation-x"
    assert not hasattr(entries[0], "reason")


def test_history_adapter_maps_postponed_status_for_recommendations(tmp_path: Path) -> None:
    repo, value = _record(tmp_path / "adapter-postponed.sqlite3")
    repo.transition(value.id, CommunicationStatus.POSTPONED, datetime(2026, 1, 2, tzinfo=UTC))
    entries = tuple(CommunicationHistoryAdapter(repo))
    assert entries[0].status is RecommendationStatus.POSTPONED
