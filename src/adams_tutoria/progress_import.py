"""Transactional import of normalized evolution records.

This boundary only applies observations to enrollments and content nodes that
already exist.  It deliberately does not reconcile students, editions, or
content hierarchy.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from adams_tutoria.domain import ImportBatch, ImportBatchStatus
from adams_tutoria.excel_contract import ProgressRecord
from adams_tutoria.persistence.database import connection


@dataclass(frozen=True, slots=True)
class ProgressImportResult:
    processed: int
    inserted: int
    unchanged: int
    rejected: int


class ProgressImportService:
    """Apply ``ProgressRecord`` observations atomically and append-only."""

    def __init__(self, path):
        self.path = path

    def apply(
        self, batch: ImportBatch, records: tuple[ProgressRecord, ...], occurred_at: datetime
    ) -> ProgressImportResult:
        with connection(self.path) as db:
            return self.apply_in_connection(db, batch, records, occurred_at)

    def apply_in_connection(
        self,
        db: sqlite3.Connection,
        batch: ImportBatch,
        records: tuple[ProgressRecord, ...],
        occurred_at: datetime,
    ) -> ProgressImportResult:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if batch.status not in (ImportBatchStatus.PENDING, ImportBatchStatus.CONFIRMED):
            raise ValueError("only pending or confirmed import batches may be applied")
        counts = [0, 0, 0, 0]
        if not self._ensure_batch(db, batch):
            return ProgressImportResult(0, 0, 0, 0)
        for record in records:
            counts[0] += 1
            outcome = self._apply_one(db, batch, record)
            counts[outcome] += 1
        db.execute(
            "UPDATE import_batch SET status='applied', finished_at=? WHERE id=?",
            (occurred_at.isoformat(), str(batch.id)),
        )
        return ProgressImportResult(*counts)

    @staticmethod
    def _ensure_batch(db: sqlite3.Connection, batch: ImportBatch) -> bool:
        existing = db.execute(
            "SELECT status FROM import_batch WHERE id=?", (str(batch.id),)
        ).fetchone()
        if existing is not None:
            return existing["status"] in ("pending", "confirmed")
        if batch.idempotency_key:
            duplicate = db.execute(
                "SELECT id FROM import_batch WHERE idempotency_key=?", (batch.idempotency_key,)
            ).fetchone()
            if duplicate is not None:
                return False
        db.execute(
            "INSERT INTO import_batch "
            "(id,source_type,source_name,started_at,finished_at,status,source_reference,"
            "source_fingerprint,context,action,group_name,total_count,accepted_count,"
            "rejected_count,warning_count,error_count,scope_type,scope_reference,idempotency_key) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
        return True

    def _apply_one(self, db: sqlite3.Connection, batch: ImportBatch, record: ProgressRecord) -> int:
        try:
            value = self._value(record.progress)
            captured_at = record.recorded_at
            if captured_at is None or captured_at.tzinfo is None or captured_at.utcoffset() is None:
                raise ValueError("recorded_at is required and must be timezone-aware")
            enrollment_id = self._enrollment_id(db, record)
            node_id = self._uuid(record.node_id, "node_id")
            node = db.execute(
                "SELECT edition_id FROM content_node WHERE id=?", (str(node_id),)
            ).fetchone()
            enrollment = db.execute(
                "SELECT edition_id FROM enrollment WHERE id=?", (str(enrollment_id),)
            ).fetchone()
            if node is None or enrollment is None:
                raise ValueError("existing enrollment and content node are required")
            if node["edition_id"] != enrollment["edition_id"]:
                raise ValueError("content node is outside enrollment edition")
            snapshot_id = uuid4()
            cursor = db.execute(
                "INSERT OR IGNORE INTO content_progress_snapshot "
                "(id,enrollment_id,node_id,captured_at,progress_percentage,external_id) "
                "VALUES(?,?,?,?,?,?)",
                (
                    str(snapshot_id),
                    str(enrollment_id),
                    str(node_id),
                    captured_at.isoformat(),
                    str(value),
                    None,
                ),
            )
            if cursor.rowcount == 0:
                self._change(db, batch, record, "unchanged", enrollment_id)
                return 2
            self._change(db, batch, record, "created", enrollment_id)
            return 1
        except (ValueError, InvalidOperation, sqlite3.IntegrityError) as error:
            self._change(db, batch, record, "rejected", None, "invalid_progress", str(error))
            return 3

    @staticmethod
    def _value(value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal("0") <= value <= Decimal("100"):
            raise ValueError("progress must be between 0 and 100")
        return value

    @staticmethod
    def _uuid(value: str | None, field: str) -> UUID:
        if value is None:
            raise ValueError(f"{field} is required")
        try:
            return UUID(value)
        except ValueError as error:
            raise ValueError(f"{field} is invalid") from error

    @classmethod
    def _enrollment_id(cls, db: sqlite3.Connection, record: ProgressRecord) -> UUID:
        if record.enrollment_id is not None:
            enrollment_id = cls._uuid(record.enrollment_id, "enrollment_id")
            if db.execute("SELECT 1 FROM enrollment WHERE id=?", (str(enrollment_id),)).fetchone():
                return enrollment_id
            raise ValueError("enrollment does not exist")
        identity = record.identity
        if identity is None or record.edition_id is None:
            raise ValueError("existing enrollment evidence is required")
        row = db.execute(
            "SELECT enrollment_id FROM enrollment_external_identity "
            "WHERE source=? AND context=? AND source_enrollment_id=? AND edition_id=?",
            (*identity.key, record.edition_id),
        ).fetchone()
        if row is None:
            raise ValueError("enrollment does not exist")
        return UUID(row["enrollment_id"])

    @staticmethod
    def _change(db, batch, record, change_type, entity_id, code=None, message=None):
        provenance = record.provenance
        db.execute(
            "INSERT INTO import_batch_change "
            "(id,batch_id,entity_type,change_type,entity_id,source_row_number,source_identifier,"
            "diagnostic_code,diagnostic_message) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                str(batch.id),
                "progress",
                change_type,
                str(entity_id) if entity_id else None,
                provenance.row_number if provenance else None,
                provenance.source_identifier if provenance else None,
                code,
                message,
            ),
        )
