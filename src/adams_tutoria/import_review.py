"""Read-only import previews and all-or-nothing human confirmation.

This module deliberately consumes normalized contracts.  It never parses an
ADAMS file and it keeps previews in memory; only a confirmed operation writes
the batch and its audit rows.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from adams_tutoria.domain import ImportBatch, ImportChangeType
from adams_tutoria.enrollment_lifecycle import EnrollmentLifecycleService
from adams_tutoria.evaluation_import import EvaluationImportService
from adams_tutoria.excel_contract import EvaluationRecord, ProgressRecord
from adams_tutoria.import_contract import ImportCandidate
from adams_tutoria.persistence.database import connection
from adams_tutoria.progress_import import ProgressImportService


@dataclass(frozen=True, slots=True)
class PreviewChange:
    entity: str
    change_type: ImportChangeType
    entity_id: UUID | None = None
    source_row_number: int | None = None
    source_identifier: str | None = None
    diagnostic_code: str | None = None
    diagnostic_message: str | None = None


@dataclass(frozen=True, slots=True)
class ImportPreview:
    preview_id: UUID
    digest: str
    state_digest: str
    created_at: datetime
    changes: tuple[PreviewChange, ...]

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    preview_id: UUID
    digest: str
    mode: str
    timestamp: datetime
    idempotency_key: str
    operator_reference: str | None = None

    def __post_init__(self) -> None:
        if self.mode != "all":
            raise ValueError("confirmation is total and mode must be 'all'")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must not be blank")


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    applied: bool
    idempotent: bool
    changes: tuple[PreviewChange, ...]
    error: str | None = None
    audit_error: str | None = None
    audit_persisted: bool = False


class PreviewStaleError(ValueError):
    """The database or the proposed normalized input changed after preview."""


class ImportReviewService:
    """Coordinate existing import services without creating editions/courses."""

    def __init__(self, path) -> None:
        self.path = path
        self._previews: dict[
            UUID,
            tuple[
                ImportBatch,
                tuple[ImportCandidate, ...],
                tuple[ProgressRecord, ...],
                tuple[EvaluationRecord, ...],
                ImportPreview,
            ],
        ] = {}

    def preview(
        self,
        batch: ImportBatch,
        *,
        candidates: Iterable[ImportCandidate] = (),
        progress: Iterable[ProgressRecord] = (),
        evaluations: Iterable[EvaluationRecord] = (),
        created_at: datetime,
    ) -> ImportPreview:
        candidates, progress, evaluations = tuple(candidates), tuple(progress), tuple(evaluations)
        with connection(self.path) as db:
            state_digest = self._state_digest(db)
            changes = self._simulate(db, batch, candidates, progress, evaluations, created_at)
            # The context manager commits unless an exception is raised.  A
            # savepoint is explicitly rolled back so preview is never durable.
            db.rollback()
        digest = self._digest(changes, state_digest, batch)
        result = ImportPreview(uuid4(), digest, state_digest, created_at, changes)
        self._previews[result.preview_id] = (batch, candidates, progress, evaluations, result)
        return result

    def confirm(self, request: ConfirmationRequest) -> ConfirmationResult:
        stored = self._previews.get(request.preview_id)
        if stored is None:
            raise KeyError("preview_id is unknown or was not retained")
        batch, candidates, progress, evaluations, preview = stored
        if request.digest != preview.digest:
            raise PreviewStaleError("preview digest does not match confirmation")
        batch = replace(batch, idempotency_key=request.idempotency_key)
        with connection(self.path) as db:
            existing = db.execute(
                "SELECT status FROM import_batch WHERE idempotency_key=?",
                (request.idempotency_key,),
            ).fetchone()
            if existing is not None:
                return ConfirmationResult(False, True, preview.changes)
            if self._state_digest(db) != preview.state_digest:
                raise PreviewStaleError("database state changed since preview")
        try:
            with connection(self.path) as db:
                changes = self._simulate(
                    db, batch, candidates, progress, evaluations, request.timestamp
                )
                if self._digest(changes, preview.state_digest, batch) != preview.digest:
                    raise PreviewStaleError("normalized input changed since preview")
                db.execute(
                    "UPDATE import_batch SET status='applied', finished_at=? WHERE id=?",
                    (request.timestamp.isoformat(), str(batch.id)),
                )
            return ConfirmationResult(True, False, preview.changes)
        except Exception as error:
            audit_error = self._persist_failure(batch, request.timestamp)
            return ConfirmationResult(
                False, False, preview.changes, str(error), audit_error, audit_error is None
            )

    def _persist_failure(self, batch: ImportBatch, occurred_at: datetime) -> str | None:
        """Recreate the rolled-back batch and record a privacy-safe global error."""
        try:
            with connection(self.path) as db:
                db.execute(
                    "INSERT INTO import_batch "
                    "(id,source_type,source_name,started_at,finished_at,status,source_reference,"
                    "source_fingerprint,context,action,group_name,total_count,accepted_count,"
                    "rejected_count,warning_count,error_count,scope_type,scope_reference,"
                    "idempotency_key) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(batch.id),
                        batch.source_type.value,
                        batch.source_name,
                        batch.started_at.isoformat(),
                        occurred_at.isoformat(),
                        "failed",
                        batch.source_reference,
                        batch.source_fingerprint,
                        batch.context,
                        batch.action,
                        batch.group,
                        batch.total_count,
                        batch.accepted_count,
                        batch.rejected_count,
                        batch.warning_count,
                        batch.error_count + 1,
                        batch.scope_type,
                        batch.scope_reference,
                        batch.idempotency_key,
                    ),
                )
                db.execute(
                    "INSERT INTO import_batch_change "
                    "(id,batch_id,entity_type,change_type,diagnostic_code,diagnostic_message) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        str(batch.id),
                        "global",
                        "error",
                        "confirmation_failed",
                        "Atomic confirmation failed; application changes were rolled back",
                    ),
                )
            return None
        except Exception as error:
            return f"{type(error).__name__}: {error}"

    @staticmethod
    def _state_digest(db) -> str:
        rows: list[tuple[str, tuple[object, ...]]] = []
        for table in (
            "course",
            "edition",
            "student",
            "enrollment",
            "enrollment_state",
            "progress_snapshot",
            "evaluation",
        ):
            rows.extend(
                (table, tuple(row)) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1")
            )
        return hashlib.sha256(repr(rows).encode()).hexdigest()

    def _simulate(self, db, batch, candidates, progress, evaluations, occurred_at):
        # Existing services share this connection through their connection-aware
        # entry points.  An exception aborts the whole transaction.
        changes: list[PreviewChange] = []
        self._ensure_batch(db, batch)
        if candidates:
            EnrollmentLifecycleService(self.path).apply_in_connection(
                db, batch, candidates, occurred_at
            )
            db.execute("UPDATE import_batch SET status='pending' WHERE id=?", (str(batch.id),))
        if progress:
            ProgressImportService(self.path).apply_in_connection(db, batch, progress, occurred_at)
            db.execute("UPDATE import_batch SET status='pending' WHERE id=?", (str(batch.id),))
        if evaluations:
            EvaluationImportService(self.path).apply_in_connection(
                db, batch, evaluations, occurred_at
            )
        for row in db.execute(
            "SELECT entity_type,change_type,entity_id,source_row_number,source_identifier,"
            "diagnostic_code,diagnostic_message FROM import_batch_change "
            "WHERE batch_id=? ORDER BY id",
            (str(batch.id),),
        ):
            kind = str(row[1]).lower()
            mapped = {
                "created": "CHANGE",
                "changed": "CHANGE",
                "modified": "CHANGE",
                "reactivated": "CHANGE",
                "unchanged": "UNCHANGED",
                "conflict": "CONFLICT",
                "rejected": "REJECTED",
                "error": "ERROR",
                "absent": "CHANGE",
            }.get(kind, "ERROR")
            changes.append(
                PreviewChange(
                    row[0],
                    ImportChangeType(mapped),
                    UUID(row[2]) if row[2] else None,
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                )
            )
        return tuple(changes)

    @staticmethod
    def _ensure_batch(db, batch: ImportBatch) -> None:
        db.execute(
            "INSERT INTO import_batch "
            "(id,source_type,source_name,started_at,finished_at,status,source_reference,"
            "source_fingerprint,context,action,group_name,total_count,accepted_count,"
            "rejected_count,warning_count,error_count,scope_type,scope_reference,idempotency_key) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (
                str(batch.id),
                batch.source_type.value,
                batch.source_name,
                batch.started_at.isoformat(),
                None,
                batch.status.value,
                batch.source_reference,
                batch.source_fingerprint,
                batch.context,
                batch.action,
                batch.group,
                batch.total_count,
                batch.accepted_count,
                batch.rejected_count,
                batch.warning_count,
                batch.error_count,
                batch.scope_type,
                batch.scope_reference,
                batch.idempotency_key,
            ),
        )

    @staticmethod
    def _digest(changes, state_digest, batch):
        payload = [
            (
                c.entity,
                c.change_type.value,
                c.source_row_number,
                c.source_identifier,
                c.diagnostic_code,
                c.diagnostic_message,
            )
            for c in changes
        ]
        return hashlib.sha256(
            json.dumps([str(batch.id), state_digest, payload], sort_keys=True).encode()
        ).hexdigest()
