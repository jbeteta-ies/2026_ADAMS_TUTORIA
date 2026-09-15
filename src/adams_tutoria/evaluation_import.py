"""Apply typed evaluation observations to existing enrollments only."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from adams_tutoria.domain import (
    EvaluationTargetType,
    ImportBatch,
    ImportBatchStatus,
)
from adams_tutoria.excel_contract import EvaluationRecord
from adams_tutoria.persistence.database import connection


@dataclass(frozen=True, slots=True)
class EvaluationImportResult:
    processed: int
    inserted: int
    changed: int
    unchanged: int
    rejected: int


class EvaluationImportService:
    """Persist evaluations with stable scoped keys and append-only history."""

    def __init__(self, path):
        self.path = path

    def apply(
        self, batch: ImportBatch, records: tuple[EvaluationRecord, ...], occurred_at: datetime
    ) -> EvaluationImportResult:
        with connection(self.path) as db:
            return self.apply_in_connection(db, batch, records, occurred_at)

    def apply_in_connection(
        self,
        db: sqlite3.Connection,
        batch: ImportBatch,
        records: tuple[EvaluationRecord, ...],
        occurred_at: datetime,
    ) -> EvaluationImportResult:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if batch.status not in (ImportBatchStatus.PENDING, ImportBatchStatus.CONFIRMED):
            raise ValueError("only pending or confirmed import batches may be applied")
        counts = [0, 0, 0, 0, 0]
        if not self._ensure_batch(db, batch):
            return EvaluationImportResult(0, 0, 0, 0, 0)
        for record in records:
            counts[0] += 1
            db.execute("SAVEPOINT evaluation_row")
            try:
                outcome = self._apply_one(db, batch, record)
                db.execute("RELEASE SAVEPOINT evaluation_row")
                counts[outcome] += 1
            except (ValueError, sqlite3.IntegrityError) as error:
                db.execute("ROLLBACK TO SAVEPOINT evaluation_row")
                db.execute("RELEASE SAVEPOINT evaluation_row")
                self._change(db, batch, record, "rejected", None, "invalid_evaluation", str(error))
                counts[4] += 1
        db.execute(
            "UPDATE import_batch SET status='applied', finished_at=? WHERE id=?",
            (occurred_at.isoformat(), str(batch.id)),
        )
        return EvaluationImportResult(*counts)

    @staticmethod
    def _ensure_batch(db: sqlite3.Connection, batch: ImportBatch) -> bool:
        row = db.execute("SELECT status FROM import_batch WHERE id=?", (str(batch.id),)).fetchone()
        if row is not None:
            return row["status"] in ("pending", "confirmed")
        if (
            batch.idempotency_key
            and db.execute(
                "SELECT 1 FROM import_batch WHERE idempotency_key=?", (batch.idempotency_key,)
            ).fetchone()
            is not None
        ):
            return False
        db.execute(
            """INSERT INTO import_batch
            (id,source_type,source_name,started_at,status,context,total_count,accepted_count,
             rejected_count,warning_count,error_count,scope_type,scope_reference,idempotency_key)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(batch.id),
                batch.source_type.value,
                batch.source_name,
                batch.started_at.isoformat(),
                batch.status.value,
                batch.context,
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

    def _apply_one(
        self, db: sqlite3.Connection, batch: ImportBatch, record: EvaluationRecord
    ) -> int:
        enrollment_id = self._enrollment_id(db, record)
        reference = record.evaluation_id or record.target
        if not reference or not reference.strip():
            raise ValueError("evaluation reference is required")
        if record.identity is None and not batch.context:
            raise ValueError("scoped evaluation identity is required")
        # The external student identifier resolves the enrollment; it is not
        # part of the evaluation identity.  Evaluations are scoped to the
        # resolved enrollment, as defined by evaluation_external_identity.
        source = record.identity.source if record.identity else batch.source_type.value
        context = record.identity.context if record.identity else batch.context
        key = (source, context, str(enrollment_id), reference)
        existing = db.execute(
            """SELECT evaluation_id FROM evaluation_external_identity
            WHERE source=? AND context=? AND enrollment_id=? AND evaluation_reference=?""",
            key,
        ).fetchone()
        evaluation_id = UUID(existing["evaluation_id"]) if existing else uuid4()
        values = self._values(record, enrollment_id, evaluation_id, reference)
        if existing is None:
            db.execute(
                """INSERT INTO evaluation
                (id,enrollment_id,target_type,target_id,status,score,max_score,passed,completed_at,
                 target_label,external_id,result_status,raw_value,numeric_value,scale)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            db.execute(
                """INSERT INTO evaluation_external_identity
                (source,context,enrollment_id,evaluation_reference,evaluation_id)
                VALUES(?,?,?,?,?)""",
                (*key, str(evaluation_id)),
            )
            self._history(db, batch, values)
            self._change(db, batch, record, "created", enrollment_id)
            return 1
        old = db.execute("SELECT * FROM evaluation WHERE id=?", (str(evaluation_id),)).fetchone()
        if tuple(old) == values:
            self._change(db, batch, record, "unchanged", enrollment_id)
            return 3
        db.execute(
            """UPDATE evaluation
            SET enrollment_id=?, target_type=?, target_id=?, status=?, score=?, max_score=?,
                passed=?, completed_at=?, target_label=?, external_id=?, result_status=?,
                raw_value=?, numeric_value=?, scale=?
            WHERE id=?""",
            (*values[1:], values[0]),
        )
        self._history(db, batch, values)
        self._change(db, batch, record, "changed", enrollment_id)
        return 2

    @staticmethod
    def _values(record, enrollment_id, evaluation_id, reference):
        return (
            str(evaluation_id),
            str(enrollment_id),
            EvaluationTargetType.ACTIVITY.value,
            reference,
            record.status.value,
            str(record.score) if record.score is not None else None,
            str(record.max_score) if record.max_score is not None else None,
            record.passed,
            record.completed_at.isoformat() if record.completed_at else None,
            record.target,
            reference,
            record.result.status.value,
            record.result.raw_value,
            str(record.result.numeric_value) if record.result.numeric_value is not None else None,
            record.result.scale,
        )

    @staticmethod
    def _history(db, batch, values):
        db.execute(
            """INSERT INTO evaluation_history
            (id,evaluation_id,batch_id,status,score,max_score,passed,completed_at,
             result_status,raw_value,numeric_value,scale)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid4()),
                values[0],
                str(batch.id),
                values[4],
                values[5],
                values[6],
                values[7],
                values[8],
                values[11],
                values[12],
                values[13],
                values[14],
            ),
        )

    @staticmethod
    def _enrollment_id(db, record):
        if record.enrollment_id:
            try:
                enrollment_id = UUID(record.enrollment_id)
            except ValueError as error:
                raise ValueError("enrollment reference is invalid") from error
            if db.execute("SELECT 1 FROM enrollment WHERE id=?", (str(enrollment_id),)).fetchone():
                return enrollment_id
            raise ValueError("enrollment does not exist")
        if record.identity and record.edition_id:
            row = db.execute(
                """SELECT enrollment_id FROM enrollment_external_identity
                WHERE source=? AND context=? AND source_enrollment_id=? AND edition_id=?""",
                (*record.identity.key, record.edition_id),
            ).fetchone()
            if row:
                return UUID(row["enrollment_id"])
        raise ValueError("existing enrollment reference is required")

    @staticmethod
    def _change(db, batch, record, kind, entity_id, code=None, message=None):
        provenance = record.provenance
        db.execute(
            "INSERT INTO import_batch_change VALUES(?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                str(batch.id),
                "evaluation",
                kind,
                str(entity_id) if entity_id else None,
                provenance.row_number if provenance else None,
                provenance.source_identifier if provenance else None,
                code,
                message,
            ),
        )
