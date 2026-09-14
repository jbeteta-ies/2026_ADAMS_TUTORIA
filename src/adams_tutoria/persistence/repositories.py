"""Small repositories with explicit mappings (no generic CRUD abstraction)."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from adams_tutoria.domain import (
    CommunicationRecord,
    CommunicationStatus,
    ContentNode,
    ContentNodeType,
    ContentProgressSnapshot,
    ContentSource,
    ContentSourceType,
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationStatus,
    EvaluationTargetType,
    ImportBatch,
    ImportBatchChange,
    ImportBatchStatus,
    ImportSourceType,
    ProgressSnapshot,
    Student,
    TutorAction,
)

from .database import connection
from .serialization import from_bool, from_date, from_datetime, from_decimal, from_enum, to_db

if TYPE_CHECKING:
    from adams_tutoria.communication_recommendations import RecommendationHistoryEntry


class _Repository:
    table: str

    def __init__(self, path: Path) -> None:
        self.path = path

    def _row(self, record_id: UUID) -> sqlite3.Row | None:
        with connection(self.path) as db:
            return db.execute(
                f"SELECT * FROM {self.table} WHERE id = ?", (str(record_id),)
            ).fetchone()


class CourseRepository(_Repository):
    table = "course"

    def save(self, value: Course) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO course(
                id,name,code,description,content_source_type,content_source_location,
                content_source_subpath,content_source_revision) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, code=excluded.code,
                description=excluded.description, content_source_type=excluded.content_source_type,
                content_source_location=excluded.content_source_location,
                content_source_subpath=excluded.content_source_subpath,
                content_source_revision=excluded.content_source_revision""",
                (
                    to_db(value.id),
                    value.name,
                    value.code,
                    value.description,
                    None
                    if value.content_source is None
                    else to_db(value.content_source.source_type),
                    None if value.content_source is None else value.content_source.location,
                    None if value.content_source is None else value.content_source.subpath,
                    None if value.content_source is None else value.content_source.revision,
                ),
            )

    def get(self, record_id: UUID) -> Course | None:
        row = self._row(record_id)
        return (
            None
            if row is None
            else Course(
                UUID(row["id"]),
                row["name"],
                row["code"],
                row["description"],
                None
                if row["content_source_type"] is None
                else ContentSource(
                    ContentSourceType(row["content_source_type"]),
                    row["content_source_location"],
                    row["content_source_subpath"],
                    row["content_source_revision"],
                ),
            )
        )


class EditionRepository(_Repository):
    table = "edition"

    def save(self, value: Edition) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO edition VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                course_id=excluded.course_id,label=excluded.label,external_id=excluded.external_id,
                start_date=excluded.start_date,end_date=excluded.end_date""",
                (
                    to_db(value.id),
                    to_db(value.course.id),
                    value.label,
                    value.external_id,
                    to_db(value.start_date),
                    to_db(value.end_date),
                ),
            )

    def get(self, record_id: UUID) -> Edition | None:
        row = self._row(record_id)
        if row is None:
            return None
        course = CourseRepository(self.path).get(UUID(row["course_id"]))
        return (
            None
            if course is None
            else Edition(
                UUID(row["id"]),
                course,
                row["label"],
                row["external_id"],
                from_date(row["start_date"]),
                from_date(row["end_date"]),
            )
        )


class StudentRepository(_Repository):
    table = "student"

    def save(self, value: Student) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO student VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                full_name=excluded.full_name,email=excluded.email,external_id=excluded.external_id""",
                (to_db(value.id), value.full_name, value.email, value.external_id),
            )

    def get(self, record_id: UUID) -> Student | None:
        row = self._row(record_id)
        return (
            None
            if row is None
            else Student(UUID(row["id"]), row["full_name"], row["email"], row["external_id"])
        )


class EnrollmentRepository(_Repository):
    table = "enrollment"

    def save(self, value: Enrollment) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO enrollment VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                student_id=excluded.student_id,edition_id=excluded.edition_id,external_id=excluded.external_id""",
                (
                    to_db(value.id),
                    to_db(value.student.id),
                    to_db(value.edition.id),
                    value.external_id,
                ),
            )

    def get(self, record_id: UUID) -> Enrollment | None:
        row = self._row(record_id)
        if row is None:
            return None
        student = StudentRepository(self.path).get(UUID(row["student_id"]))
        edition = EditionRepository(self.path).get(UUID(row["edition_id"]))
        return (
            None
            if student is None or edition is None
            else Enrollment(UUID(row["id"]), student, edition, row["external_id"])
        )


class ProgressSnapshotRepository(_Repository):
    table = "progress_snapshot"

    def save(self, value: ProgressSnapshot) -> None:
        with connection(self.path) as db:
            db.execute(
                "INSERT INTO progress_snapshot VALUES(?,?,?,?,?)",
                (
                    to_db(value.id),
                    to_db(value.enrollment.id),
                    to_db(value.captured_at),
                    to_db(value.progress_percentage),
                    value.external_id,
                ),
            )

    def get(self, record_id: UUID) -> ProgressSnapshot | None:
        row = self._row(record_id)
        enrollment = (
            None if row is None else EnrollmentRepository(self.path).get(UUID(row["enrollment_id"]))
        )
        return (
            None
            if row is None or enrollment is None
            else ProgressSnapshot(
                UUID(row["id"]),
                enrollment,
                datetime.fromisoformat(row["captured_at"]),
                Decimal(row["progress_percentage"]),
                row["external_id"],
            )
        )

    def list_for_enrollment(self, enrollment_id: UUID) -> tuple[ProgressSnapshot, ...]:
        with connection(self.path) as db:
            ids = [
                UUID(row["id"])
                for row in db.execute(
                    "SELECT id FROM progress_snapshot WHERE enrollment_id = ? "
                    "ORDER BY captured_at, id",
                    (str(enrollment_id),),
                )
            ]
        return tuple(record for record_id in ids if (record := self.get(record_id)) is not None)


class ContentNodeRepository(_Repository):
    table = "content_node"

    def save(self, value: ContentNode) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO content_node
                (id,course_id,edition_id,node_type,title,parent_id,external_id)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                course_id=excluded.course_id,edition_id=excluded.edition_id,
                node_type=excluded.node_type,title=excluded.title,parent_id=excluded.parent_id,
                external_id=excluded.external_id""",
                (
                    to_db(value.id),
                    to_db(value.course.id),
                    to_db(value.edition.id),
                    to_db(value.node_type),
                    value.title,
                    to_db(value.parent.id) if value.parent else None,
                    value.external_id,
                ),
            )

    def get(self, record_id: UUID) -> ContentNode | None:
        row = self._row(record_id)
        if row is None:
            return None
        course = CourseRepository(self.path).get(UUID(row["course_id"]))
        edition = EditionRepository(self.path).get(UUID(row["edition_id"]))
        parent = self.get(UUID(row["parent_id"])) if row["parent_id"] else None
        return (
            None
            if course is None or edition is None
            else ContentNode(
                UUID(row["id"]),
                course,
                edition,
                ContentNodeType(row["node_type"]),
                row["title"],
                parent,
                row["external_id"],
            )
        )

    def list_for_edition(self, edition_id: UUID) -> tuple[ContentNode, ...]:
        with connection(self.path) as db:
            ids = [
                UUID(row["id"])
                for row in db.execute(
                    "SELECT id FROM content_node WHERE edition_id = ? ORDER BY id",
                    (str(edition_id),),
                )
            ]
        return tuple(record for record_id in ids if (record := self.get(record_id)) is not None)


class ContentProgressSnapshotRepository(_Repository):
    table = "content_progress_snapshot"

    def save(self, value: ContentProgressSnapshot) -> None:
        with connection(self.path) as db:
            db.execute(
                "INSERT INTO content_progress_snapshot VALUES(?,?,?,?,?,?)",
                (
                    to_db(value.id),
                    to_db(value.enrollment.id),
                    to_db(value.node.id),
                    to_db(value.captured_at),
                    to_db(value.progress_percentage),
                    value.external_id,
                ),
            )

    def get(self, record_id: UUID) -> ContentProgressSnapshot | None:
        row = self._row(record_id)
        if row is None:
            return None
        enrollment = EnrollmentRepository(self.path).get(UUID(row["enrollment_id"]))
        node = ContentNodeRepository(self.path).get(UUID(row["node_id"]))
        return (
            None
            if enrollment is None or node is None
            else ContentProgressSnapshot(
                UUID(row["id"]),
                enrollment,
                node,
                datetime.fromisoformat(row["captured_at"]),
                Decimal(row["progress_percentage"]),
                row["external_id"],
            )
        )

    def list_for_enrollment_and_node(
        self, enrollment_id: UUID, node_id: UUID
    ) -> tuple[ContentProgressSnapshot, ...]:
        with connection(self.path) as db:
            ids = [
                UUID(row["id"])
                for row in db.execute(
                    "SELECT id FROM content_progress_snapshot "
                    "WHERE enrollment_id = ? AND node_id = ? ORDER BY captured_at, id",
                    (str(enrollment_id), str(node_id)),
                )
            ]
        return tuple(record for record_id in ids if (record := self.get(record_id)) is not None)


class EvaluationRepository(_Repository):
    table = "evaluation"

    def save(self, value: Evaluation) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO evaluation VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                enrollment_id=excluded.enrollment_id,target_type=excluded.target_type,target_id=excluded.target_id,
                status=excluded.status,score=excluded.score,max_score=excluded.max_score,passed=excluded.passed,
                completed_at=excluded.completed_at,target_label=excluded.target_label,
                external_id=excluded.external_id""",
                (
                    to_db(value.id),
                    to_db(value.enrollment.id),
                    to_db(value.target_type),
                    value.target_id,
                    to_db(value.status),
                    to_db(value.score),
                    to_db(value.max_score),
                    to_db(value.passed),
                    to_db(value.completed_at),
                    value.target_label,
                    value.external_id,
                ),
            )

    def get(self, record_id: UUID) -> Evaluation | None:
        row = self._row(record_id)
        if row is None:
            return None
        enrollment = EnrollmentRepository(self.path).get(UUID(row["enrollment_id"]))
        return (
            None
            if enrollment is None
            else Evaluation(
                UUID(row["id"]),
                enrollment,
                from_enum(EvaluationTargetType, row["target_type"]),
                row["target_id"],
                from_enum(EvaluationStatus, row["status"]),
                from_decimal(row["score"]),
                from_decimal(row["max_score"]),
                from_bool(row["passed"]),
                from_datetime(row["completed_at"]),
                row["target_label"],
                row["external_id"],
            )
        )

    def list_for_enrollment(self, enrollment_id: UUID) -> tuple[Evaluation, ...]:
        with connection(self.path) as db:
            ids = [
                UUID(row["id"])
                for row in db.execute(
                    "SELECT id FROM evaluation WHERE enrollment_id = ? ORDER BY id",
                    (str(enrollment_id),),
                )
            ]
        return tuple(record for record_id in ids if (record := self.get(record_id)) is not None)


class TutorActionRepository(_Repository):
    """Persistence for tutor workflow logs, kept separate from personal data."""

    table = "tutor_action"

    def save(self, value: TutorAction) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO tutor_action VALUES(?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET enrollment_id=excluded.enrollment_id,
                occurred_at=excluded.occurred_at, action=excluded.action, note=excluded.note""",
                (
                    to_db(value.id),
                    to_db(value.enrollment_id),
                    to_db(value.occurred_at),
                    value.action,
                    value.note,
                ),
            )

    def get(self, record_id: UUID) -> TutorAction | None:
        row = self._row(record_id)
        return (
            None
            if row is None
            else TutorAction(
                UUID(row["id"]),
                UUID(row["enrollment_id"]),
                datetime.fromisoformat(row["occurred_at"]),
                row["action"],
                row["note"],
            )
        )

    def list_for_enrollment(self, enrollment_id: UUID) -> tuple[TutorAction, ...]:
        with connection(self.path) as db:
            ids = [
                UUID(row["id"])
                for row in db.execute(
                    "SELECT id FROM tutor_action WHERE enrollment_id = ? ORDER BY occurred_at, id",
                    (str(enrollment_id),),
                )
            ]
        return tuple(record for record_id in ids if (record := self.get(record_id)) is not None)


class ImportBatchRepository(_Repository):
    """Explicit repository for safe import execution metadata."""

    table = "import_batch"

    _allowed = {
        ImportBatchStatus.PENDING: {
            ImportBatchStatus.CONFIRMED,
            ImportBatchStatus.REJECTED,
            ImportBatchStatus.FAILED,
        },
        ImportBatchStatus.CONFIRMED: {
            ImportBatchStatus.APPLIED,
            ImportBatchStatus.REJECTED,
            ImportBatchStatus.FAILED,
        },
        ImportBatchStatus.APPLIED: set(),
        ImportBatchStatus.REJECTED: set(),
        ImportBatchStatus.FAILED: set(),
    }

    def save(self, value: ImportBatch) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO import_batch
                (id,source_type,source_name,started_at,finished_at,status,source_reference,
                 source_fingerprint,context,action,group_name,total_count,accepted_count,
                 rejected_count,warning_count,error_count,scope_type,scope_reference,idempotency_key)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET source_type=excluded.source_type,
                source_name=excluded.source_name,started_at=excluded.started_at,finished_at=excluded.finished_at,
                status=excluded.status,source_reference=excluded.source_reference,
                source_fingerprint=excluded.source_fingerprint,context=excluded.context,action=excluded.action,
                group_name=excluded.group_name,total_count=excluded.total_count,accepted_count=excluded.accepted_count,
                 rejected_count=excluded.rejected_count,warning_count=excluded.warning_count,
                 error_count=excluded.error_count,scope_type=excluded.scope_type,
                 scope_reference=excluded.scope_reference,idempotency_key=excluded.idempotency_key""",
                (
                    to_db(value.id),
                    to_db(value.source_type),
                    value.source_name,
                    to_db(value.started_at),
                    to_db(value.finished_at),
                    to_db(value.status),
                    value.source_reference,
                    value.source_fingerprint,
                    value.context,
                    value.action,
                    value.group,
                    value.total_count,
                    value.accepted_count,
                    value.rejected_count,
                    value.warning_count,
                    value.error_count,
                    value.scope_type,
                    value.scope_reference,
                    value.idempotency_key,
                ),
            )

    def get(self, record_id: UUID) -> ImportBatch | None:
        row = self._row(record_id)
        return (
            None
            if row is None
            else ImportBatch(
                UUID(row["id"]),
                ImportSourceType(row["source_type"]),
                row["source_name"],
                datetime.fromisoformat(row["started_at"]),
                ImportBatchStatus(row["status"]),
                from_datetime(row["finished_at"]),
                row["source_reference"],
                row["source_fingerprint"],
                row["context"],
                row["action"],
                row["group_name"],
                row["total_count"],
                row["accepted_count"],
                row["rejected_count"],
                row["warning_count"],
                row["error_count"],
                row["scope_type"] if "scope_type" in tuple(row.keys()) else "partial",
                row["scope_reference"] if "scope_reference" in tuple(row.keys()) else None,
                row["idempotency_key"] if "idempotency_key" in tuple(row.keys()) else None,
            )
        )

    def transition(self, record_id: UUID, status: ImportBatchStatus, occurred_at: datetime) -> None:
        record = self.get(record_id)
        if record is None:
            raise KeyError(record_id)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if status not in self._allowed[record.status]:
            raise ValueError(f"invalid import transition: {record.status.value} -> {status.value}")
        if occurred_at < record.started_at:
            raise ValueError("transition timestamp must not be before started_at")
        self.save(
            ImportBatch(
                record.id,
                record.source_type,
                record.source_name,
                record.started_at,
                status,
                occurred_at
                if status
                in (ImportBatchStatus.APPLIED, ImportBatchStatus.REJECTED, ImportBatchStatus.FAILED)
                else record.finished_at,
                record.source_reference,
                record.source_fingerprint,
                record.context,
                record.action,
                record.group,
                record.total_count,
                record.accepted_count,
                record.rejected_count,
                record.warning_count,
                record.error_count,
                record.scope_type,
                record.scope_reference,
                record.idempotency_key,
            )
        )


class ImportBatchChangeRepository(_Repository):
    table = "import_batch_change"

    def save(self, value: ImportBatchChange) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO import_batch_change
                (id,batch_id,entity_type,change_type,entity_id,source_row_number,source_identifier,
                 diagnostic_code,diagnostic_message) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET batch_id=excluded.batch_id,
                entity_type=excluded.entity_type,
                change_type=excluded.change_type,entity_id=excluded.entity_id,source_row_number=excluded.source_row_number,
                source_identifier=excluded.source_identifier,diagnostic_code=excluded.diagnostic_code,
                diagnostic_message=excluded.diagnostic_message""",
                (
                    to_db(value.id),
                    to_db(value.batch_id),
                    value.entity_type,
                    value.change_type,
                    to_db(value.entity_id),
                    value.source_row_number,
                    value.source_identifier,
                    value.diagnostic_code,
                    value.diagnostic_message,
                ),
            )

    def get(self, record_id: UUID) -> ImportBatchChange | None:
        row = self._row(record_id)
        return (
            None
            if row is None
            else ImportBatchChange(
                UUID(row["id"]),
                UUID(row["batch_id"]),
                row["entity_type"],
                row["change_type"],
                UUID(row["entity_id"]) if row["entity_id"] else None,
                row["source_row_number"],
                row["source_identifier"],
                row["diagnostic_code"],
                row["diagnostic_message"],
            )
        )

    def list_for_batch(self, batch_id: UUID) -> tuple[ImportBatchChange, ...]:
        with connection(self.path) as db:
            ids = [
                UUID(row["id"])
                for row in db.execute(
                    "SELECT id FROM import_batch_change WHERE batch_id = ? ORDER BY id",
                    (str(batch_id),),
                )
            ]
        return tuple(record for record_id in ids if (record := self.get(record_id)) is not None)


class CommunicationRecordRepository(_Repository):
    table = "communication_record"

    def save(self, value: CommunicationRecord) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO communication_record
                (id,enrollment_id,communication_type,reason,suggested_at,status,reviewed_at,sent_at,
                 deduplication_key,context_key,recommendation_id,trigger,edition_id,postponed_at,copied_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                enrollment_id=excluded.enrollment_id,communication_type=excluded.communication_type,reason=excluded.reason,
                suggested_at=excluded.suggested_at,status=excluded.status,reviewed_at=excluded.reviewed_at,
                sent_at=excluded.sent_at,deduplication_key=excluded.deduplication_key,context_key=excluded.context_key,
                recommendation_id=excluded.recommendation_id,trigger=excluded.trigger,edition_id=excluded.edition_id,
                postponed_at=excluded.postponed_at,copied_at=excluded.copied_at""",
                (
                    to_db(value.id),
                    to_db(value.enrollment.id),
                    value.communication_type,
                    value.reason,
                    to_db(value.suggested_at),
                    to_db(value.status),
                    to_db(value.reviewed_at),
                    to_db(value.sent_at),
                    value.deduplication_key,
                    value.context_key,
                    value.recommendation_id,
                    value.trigger,
                    to_db(value.edition_id),
                    to_db(value.postponed_at),
                    to_db(value.copied_at),
                ),
            )

    def get(self, record_id: UUID) -> CommunicationRecord | None:
        row = self._row(record_id)
        if row is None:
            return None
        enrollment = EnrollmentRepository(self.path).get(UUID(row["enrollment_id"]))
        columns = set(row.keys())
        return (
            None
            if enrollment is None
            else CommunicationRecord(
                UUID(row["id"]),
                enrollment,
                row["communication_type"],
                row["reason"],
                datetime.fromisoformat(row["suggested_at"]),
                from_enum(CommunicationStatus, row["status"]),
                from_datetime(row["reviewed_at"]),
                from_datetime(row["sent_at"]),
                row["deduplication_key"],
                row["context_key"],
                row["recommendation_id"] if "recommendation_id" in columns else None,
                row["trigger"] if "trigger" in columns else None,
                UUID(row["edition_id"])
                if "edition_id" in columns and row["edition_id"]
                else enrollment.edition.id,
                from_datetime(row["postponed_at"]) if "postponed_at" in columns else None,
                from_datetime(row["copied_at"]) if "copied_at" in columns else None,
            )
        )

    def list_for_enrollment(
        self, enrollment_id: UUID, edition_id: UUID | None = None
    ) -> tuple[CommunicationRecord, ...]:
        with connection(self.path) as db:
            query = "SELECT id FROM communication_record WHERE enrollment_id = ?"
            parameters: list[str] = [str(enrollment_id)]
            if edition_id is not None:
                query += " AND (edition_id = ? OR edition_id IS NULL)"
                parameters.append(str(edition_id))
            query += " ORDER BY suggested_at, id"
            ids = [UUID(row["id"]) for row in db.execute(query, parameters)]
        return tuple(record for record_id in ids if (record := self.get(record_id)) is not None)

    def transition(
        self, record_id: UUID, status: CommunicationStatus, occurred_at: datetime
    ) -> None:
        record = self.get(record_id)
        if record is None:
            raise KeyError(record_id)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        allowed = {
            CommunicationStatus.SUGGESTED: {
                CommunicationStatus.APPROVED,
                CommunicationStatus.DISCARDED,
                CommunicationStatus.POSTPONED,
            },
            CommunicationStatus.POSTPONED: {
                CommunicationStatus.APPROVED,
                CommunicationStatus.DISCARDED,
            },
            CommunicationStatus.APPROVED: {CommunicationStatus.COPIED, CommunicationStatus.SENT},
            CommunicationStatus.COPIED: {CommunicationStatus.SENT},
            CommunicationStatus.DISCARDED: set(),
            CommunicationStatus.SENT: set(),
        }
        if status not in allowed[record.status]:
            raise ValueError(
                f"invalid communication transition: {record.status.value} -> {status.value}"
            )
        if occurred_at < record.suggested_at:
            raise ValueError("transition timestamp must not be before suggested_at")
        if record.postponed_at is not None and occurred_at < record.postponed_at:
            raise ValueError("transition timestamp must not be before postponed_at")
        reviewed_at = (
            occurred_at
            if status in (CommunicationStatus.APPROVED, CommunicationStatus.DISCARDED)
            else record.reviewed_at
        )
        sent_at = occurred_at if status is CommunicationStatus.SENT else record.sent_at
        postponed_at = (
            occurred_at
            if status is CommunicationStatus.POSTPONED
            else None
            if status in (CommunicationStatus.COPIED, CommunicationStatus.SENT)
            else record.postponed_at
        )
        copied_at = occurred_at if status is CommunicationStatus.COPIED else record.copied_at
        self.save(
            CommunicationRecord(
                record.id,
                record.enrollment,
                record.communication_type,
                record.reason,
                record.suggested_at,
                status,
                reviewed_at,
                sent_at,
                record.deduplication_key,
                record.context_key,
                record.recommendation_id,
                record.trigger,
                record.edition_id,
                postponed_at,
                copied_at,
            )
        )


class CommunicationHistoryAdapter:
    """Read-only projection for the #20 recommendation history port."""

    def __init__(
        self,
        repository: CommunicationRecordRepository,
        enrollment_id: UUID | None = None,
        edition_id: UUID | None = None,
    ) -> None:
        self.repository, self.enrollment_id, self.edition_id = repository, enrollment_id, edition_id

    def __iter__(self) -> Iterator["RecommendationHistoryEntry"]:
        from adams_tutoria.communication_recommendations import (
            RecommendationHistoryEntry,
            RecommendationStatus,
        )

        with connection(self.repository.path) as db:
            query = "SELECT id FROM communication_record WHERE 1=1"
            params: list[str] = []
            if self.enrollment_id is not None:
                query += " AND enrollment_id = ?"
                params.append(str(self.enrollment_id))
            if self.edition_id is not None:
                query += " AND (edition_id = ? OR edition_id IS NULL)"
                params.append(str(self.edition_id))
            query += " ORDER BY suggested_at, id"
            ids = [UUID(row["id"]) for row in db.execute(query, params)]
        for record_id in ids:
            record = self.repository.get(record_id)
            if record is not None and record.recommendation_id is not None:
                yield RecommendationHistoryEntry(
                    record.recommendation_id,
                    record.enrollment.id,
                    record.edition_id or record.enrollment.edition.id,
                    record.communication_type,
                    record.suggested_at,
                    {
                        CommunicationStatus.POSTPONED: RecommendationStatus.POSTPONED,
                    }.get(record.status, record.status),
                )
