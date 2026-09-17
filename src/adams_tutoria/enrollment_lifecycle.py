"""Transactional, append-only lifecycle for imported students and enrollments."""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from adams_tutoria.domain import ImportBatch, ImportBatchStatus
from adams_tutoria.import_contract import ImportCandidate
from adams_tutoria.persistence.database import connection


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    processed: int
    created: int
    modified: int
    unchanged: int
    absent: int
    deactivated: int
    reactivated: int
    conflicts: int


class EnrollmentLifecycleService:
    """Apply already-normalized candidates; parsing and course creation are out of scope."""

    def __init__(self, path):
        self.path = path

    def apply(
        self, batch: ImportBatch, candidates: Iterable[ImportCandidate], occurred_at: datetime
    ) -> LifecycleResult:
        with connection(self.path) as db:
            return self.apply_in_connection(db, batch, candidates, occurred_at)

    def apply_in_connection(
        self,
        db: sqlite3.Connection,
        batch: ImportBatch,
        candidates: Iterable[ImportCandidate],
        occurred_at: datetime,
    ) -> LifecycleResult:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        candidates = tuple(candidates)
        if batch.status not in (ImportBatchStatus.PENDING, ImportBatchStatus.CONFIRMED):
            raise ValueError("only pending or confirmed import batches may be applied")
        if batch.scope_type == "full" and not batch.scope_reference:
            raise ValueError("a full batch requires scope_reference")
        counts = [0] * 8
        if not self._ensure_batch(db, batch):
            return LifecycleResult(0, 0, 0, 0, 0, 0, 0, 0)
        self._validate_scope(db, batch, candidates)
        seen: set[tuple[str, str, str, str]] = set()
        for candidate in candidates:
            present_key = self._enrollment_key(candidate)
            if present_key is not None:
                seen.add(present_key)
            result = self._apply_one(db, batch, candidate, occurred_at, seen)
            counts[0] += 1
            counts[result] += 1
        absent = deactivated = 0
        if batch.scope_type == "full":
            rows = db.execute(
                "SELECT ee.source, ee.context, ee.source_enrollment_id, "
                "ee.edition_id, ee.enrollment_id "
                "FROM enrollment_external_identity ee LEFT JOIN enrollment_state es "
                "ON es.enrollment_id=ee.enrollment_id "
                "WHERE ee.edition_id=? AND COALESCE(es.active, 1)=1",
                (batch.scope_reference,),
            ).fetchall()
            for row in rows:
                key = (
                    row["source"],
                    row["context"],
                    row["source_enrollment_id"],
                    row["edition_id"],
                )
                if key not in seen:
                    self._state(db, batch, UUID(row["enrollment_id"]), False, occurred_at, "absent")
                    self._change(
                        db,
                        batch,
                        "enrollment",
                        "absent",
                        UUID(row["enrollment_id"]),
                        diagnostic="absent_from_full_scope",
                        diagnostic_message="Enrollment was not present in the full batch scope",
                    )
                    absent += 1
                    deactivated += 1
            counts[4], counts[5] = absent, deactivated
        db.execute(
            "UPDATE import_batch SET status='applied', finished_at=? WHERE id=?",
            (occurred_at.isoformat(), str(batch.id)),
        )
        return LifecycleResult(*counts)

    @staticmethod
    def _enrollment_key(candidate):
        """Return the stable composite key when candidate evidence is sufficient."""
        if candidate.entity.value != "enrollment" or candidate.enrollment is None:
            return None
        evidence = candidate.enrollment
        student = evidence.student
        identity = student.external_identity if student else None
        edition = evidence.edition.edition_reference if evidence.edition else None
        if identity is None or edition is None or edition.reference is None:
            return None
        reference = evidence.enrollment_reference
        enrollment_id = (
            str(reference.reference)
            if reference and reference.reference
            else dict(candidate.values).get("source_enrollment_id") or identity.source_student_id
        )
        return (identity.source, identity.context, enrollment_id, str(edition.reference))

    @staticmethod
    def _validate_scope(db, batch, candidates) -> None:
        """Reject references outside the declared, existing edition scope."""
        if batch.scope_reference:
            edition = db.execute(
                "SELECT id FROM edition WHERE id=?", (batch.scope_reference,)
            ).fetchone()
            if edition is None:
                raise ValueError("scope_reference must identify an existing edition")
        if not batch.scope_reference:
            return
        for candidate in candidates:
            evidence = candidate.enrollment if candidate.entity.value == "enrollment" else None
            edition = evidence.edition if evidence else candidate.edition
            reference = edition.edition_reference if edition else None
            if (
                reference
                and reference.reference is not None
                and str(reference.reference) != batch.scope_reference
            ):
                raise ValueError("candidate edition is outside the full batch scope")

    @staticmethod
    def _ensure_batch(db: sqlite3.Connection, batch: ImportBatch) -> bool:
        by_id = db.execute(
            "SELECT id, status FROM import_batch WHERE id=?", (str(batch.id),)
        ).fetchone()
        if by_id:
            return by_id["status"] in ("pending", "confirmed")
        existing = (
            db.execute(
                "SELECT id FROM import_batch WHERE idempotency_key=?", (batch.idempotency_key,)
            ).fetchone()
            if batch.idempotency_key
            else None
        )
        if existing and existing["id"] != str(batch.id):
            raise ValueError("idempotency key already belongs to another batch")
        if existing:
            return False
        db.execute(
            "INSERT INTO import_batch(id,source_type,source_name,started_at,finished_at,status,source_reference,source_fingerprint,context,action,group_name,total_count,accepted_count,rejected_count,warning_count,error_count,scope_type,scope_reference,idempotency_key) "  # noqa: E501
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (
                str(batch.id),
                batch.source_type.value,
                batch.source_name,
                batch.started_at.isoformat(),
                batch.finished_at.isoformat() if batch.finished_at else None,
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

    def _apply_one(
        self,
        db: sqlite3.Connection,
        batch: ImportBatch,
        candidate: ImportCandidate,
        occurred_at: datetime,
        seen: set[tuple[str, str, str, str]],
    ) -> int:
        enrollment_evidence = (
            candidate.enrollment if candidate.entity.value == "enrollment" else None
        )
        student_evidence = enrollment_evidence.student if enrollment_evidence else candidate.student
        if (
            candidate.entity.value not in ("student", "enrollment")
            or student_evidence is None
            or student_evidence.external_identity is None
        ):
            return self._change(
                db, batch, "candidate", "conflict", None, candidate, "missing_external_identity"
            )
        identity = student_evidence.external_identity
        edition_evidence = enrollment_evidence.edition if enrollment_evidence else candidate.edition
        edition = edition_evidence.edition_reference if edition_evidence else None
        enrollment_key: str | None = None
        edition_id: str | None = None
        existing_enrollment = None
        if candidate.entity.value == "enrollment":
            assert enrollment_evidence is not None
            if edition is None or edition.reference is None:
                return self._change(
                    db,
                    batch,
                    "enrollment",
                    "conflict",
                    None,
                    candidate,
                    "missing_edition",
                    "Enrollment candidate has no existing edition reference",
                )
            edition_id = str(edition.reference)
            enrollment_reference = enrollment_evidence.enrollment_reference
            enrollment_key = (
                str(enrollment_reference.reference)
                if enrollment_reference and enrollment_reference.reference
                else (
                    dict(candidate.values).get("source_enrollment_id") or identity.source_student_id
                )
            )
            existing_enrollment = db.execute(
                "SELECT e.id, e.student_id FROM enrollment_external_identity x "
                "JOIN enrollment e ON e.id=x.enrollment_id "
                "WHERE x.source=? AND x.context=? AND x.source_enrollment_id=? AND x.edition_id=?",
                (identity.source, identity.context, enrollment_key, edition_id),
            ).fetchone()
        student_row = db.execute(
            "SELECT s.* FROM student_external_identity x JOIN student s ON s.id=x.student_id "  # noqa: E501
            "WHERE x.source=? AND x.context=? AND x.source_student_id=?",
            identity.key,
        ).fetchone()
        student_modified = False
        if student_row is None:
            if existing_enrollment is not None:
                return self._change(
                    db,
                    batch,
                    "enrollment",
                    "conflict",
                    UUID(existing_enrollment["id"]),
                    candidate,
                    "enrollment_student_mismatch",
                    "Enrollment identity belongs to a different student",
                )
            if not student_evidence.name:
                return self._change(
                    db,
                    batch,
                    "student",
                    "conflict",
                    None,
                    candidate,
                    "missing_name",
                    "Enrollment candidate has no student name",
                )
            student_id = uuid4()
            db.execute(
                "INSERT INTO student(id,full_name,email) VALUES(?,?,?)",
                (str(student_id), student_evidence.name.strip(), student_evidence.email),
            )
            db.execute(
                "INSERT INTO student_external_identity VALUES(?,?,?,?)",
                (*identity.key, str(student_id)),
            )
            self._history(
                db,
                batch,
                "student",
                student_id,
                "created",
                occurred_at,
                student_evidence.name,
                student_evidence.email,
            )
            event = "created"
        else:
            student_id = UUID(student_row["id"])
            name = student_evidence.name.strip() if student_evidence.name else None
            email = student_evidence.email
            if candidate.action != "snapshot" and (
                (name is not None and name != student_row["full_name"])
                or (email is not None and email != (student_row["email"] or ""))
            ):
                return self._change(
                    db,
                    batch,
                    "student",
                    "conflict",
                    student_id,
                    candidate,
                    "identity_attributes_conflict",
                    "Candidate identity attributes conflict with stored identity",
                )
            updates = {}
            if (
                name is not None
                and name != student_row["full_name"]
                and candidate.action == "snapshot"
            ):
                updates["full_name"] = name
            if not student_row["email"] and email:
                updates["email"] = email
            if updates:
                db.execute(
                    "UPDATE student SET full_name=COALESCE(?,full_name), "
                    "email=COALESCE(?,email) WHERE id=?",
                    (updates.get("full_name"), updates.get("email"), str(student_id)),
                )
                self._history(
                    db,
                    batch,
                    "student",
                    student_id,
                    "modified",
                    occurred_at,
                    updates.get("full_name"),
                    updates.get("email"),
                )
                event = "modified"
                student_modified = True
            else:
                event = "unchanged"
        if candidate.entity.value == "student":
            return self._change(db, batch, "student", event, student_id, candidate)
        assert enrollment_key is not None
        assert edition_id is not None
        if existing_enrollment is not None and existing_enrollment["student_id"] != str(student_id):
            return self._change(
                db,
                batch,
                "enrollment",
                "conflict",
                UUID(existing_enrollment["id"]),
                candidate,
                "enrollment_student_mismatch",
                "Enrollment identity belongs to a different student",
            )
        row = existing_enrollment
        if row is None:
            enrollment_id = uuid4()
            enrollment_external_id = dict(candidate.values).get("enrollment_external_id")
            db.execute(
                "INSERT INTO enrollment(id,student_id,edition_id,external_id) VALUES(?,?,?,?)",
                (str(enrollment_id), str(student_id), edition_id, enrollment_external_id),
            )
            db.execute(
                "INSERT INTO enrollment_external_identity VALUES(?,?,?,?,?)",
                (identity.source, identity.context, enrollment_key, edition_id, str(enrollment_id)),
            )
            db.execute(
                "INSERT INTO enrollment_state VALUES(?,?,?)",
                (str(enrollment_id), 1, occurred_at.isoformat()),
            )
            self._history(
                db, batch, "enrollment", enrollment_id, "created", occurred_at, active=True
            )
            event, active = "created", True
        else:
            enrollment_id = UUID(row["id"])
            supplied_external_id = dict(candidate.values).get("enrollment_external_id")
            enrollment_record = db.execute(
                "SELECT external_id FROM enrollment WHERE id=?", (str(enrollment_id),)
            ).fetchone()
            if supplied_external_id and enrollment_record["external_id"] not in (
                None,
                supplied_external_id,
            ):
                return self._change(
                    db,
                    batch,
                    "enrollment",
                    "conflict",
                    enrollment_id,
                    candidate,
                    "enrollment_attributes_conflict",
                    "Candidate enrollment attributes conflict with stored enrollment",
                )
            enrollment_modified = supplied_external_id and enrollment_record["external_id"] is None
            if enrollment_modified:
                db.execute(
                    "UPDATE enrollment SET external_id=? WHERE id=?",
                    (supplied_external_id, str(enrollment_id)),
                )
                self._history(
                    db,
                    batch,
                    "enrollment",
                    enrollment_id,
                    "modified",
                    occurred_at,
                    external_id=supplied_external_id,
                )
            state = db.execute(
                "SELECT active FROM enrollment_state WHERE enrollment_id=?", (str(enrollment_id),)
            ).fetchone()
            active = bool(state["active"]) if state else True
            explicit_reactivation = candidate.action in ("reactivate", "snapshot")
            if not active and not explicit_reactivation:
                return self._change(
                    db,
                    batch,
                    "enrollment",
                    "conflict",
                    enrollment_id,
                    candidate,
                    "reactivation_required",
                    "Inactive enrollment requires explicit reactivation",
                )
            event = (
                "reactivated"
                if not active
                else ("modified" if enrollment_modified or student_modified else "unchanged")
            )
            if not active:
                self._state(db, batch, enrollment_id, True, occurred_at, event)
        return self._change(db, batch, "enrollment", event, enrollment_id, candidate)

    @staticmethod
    def _state(db, batch, enrollment_id, active, occurred_at, event):
        db.execute(
            "INSERT OR REPLACE INTO enrollment_state VALUES(?,?,?)",
            (str(enrollment_id), int(active), occurred_at.isoformat()),
        )
        EnrollmentLifecycleService._history(
            db, batch, "enrollment", enrollment_id, event, occurred_at, active=active
        )

    @staticmethod
    def _history(
        db,
        batch,
        entity,
        entity_id,
        event,
        occurred_at,
        full_name=None,
        email=None,
        active=True,
        external_id=None,
    ):
        if entity == "student":
            db.execute(
                "INSERT INTO student_history VALUES(?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    str(entity_id),
                    str(batch.id),
                    event,
                    full_name,
                    email,
                    occurred_at.isoformat(),
                ),
            )
        else:
            db.execute(
                "INSERT INTO enrollment_history "
                "(id,enrollment_id,batch_id,event_type,active,external_id,occurred_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    str(entity_id),
                    str(batch.id),
                    event,
                    int(active),
                    external_id,
                    occurred_at.isoformat(),
                ),
            )

    @staticmethod
    def _change(
        db,
        batch,
        entity,
        event,
        entity_id,
        candidate=None,
        diagnostic=None,
        diagnostic_message=None,
    ):
        messages = {
            "missing_external_identity": "Stable external student identity is required",
        }
        db.execute(
            "INSERT INTO import_batch_change(id,batch_id,entity_type,change_type,entity_id,source_row_number,source_identifier,diagnostic_code,diagnostic_message) VALUES(?,?,?,?,?,?,?,?,?)",  # noqa: E501
            (
                str(uuid4()),
                str(batch.id),
                entity,
                event,
                str(entity_id) if entity_id else None,
                candidate.provenance.row_number if candidate else None,
                candidate.provenance.source_identifier if candidate else None,
                diagnostic,
                diagnostic_message or messages.get(diagnostic, diagnostic),
            ),
        )
        return {
            "created": 1,
            "modified": 2,
            "unchanged": 3,
            "absent": 4,
            "deactivated": 5,
            "reactivated": 6,
            "conflict": 7,
        }.get(event, 3)
