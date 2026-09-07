"""Small repositories with explicit mappings (no generic CRUD abstraction)."""

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from adams_tutoria.domain import (
    CommunicationRecord,
    CommunicationStatus,
    Course,
    Edition,
    Enrollment,
    Evaluation,
    EvaluationStatus,
    EvaluationTargetType,
    ProgressSnapshot,
    Student,
)

from .database import connection
from .serialization import from_bool, from_date, from_datetime, from_decimal, from_enum, to_db


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
                """INSERT INTO course(id,name,code,description) VALUES(?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, code=excluded.code,
                description=excluded.description""",
                (to_db(value.id), value.name, value.code, value.description),
            )

    def get(self, record_id: UUID) -> Course | None:
        row = self._row(record_id)
        return (
            None
            if row is None
            else Course(UUID(row["id"]), row["name"], row["code"], row["description"])
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
                "INSERT INTO progress_snapshot VALUES(?,?,?,?)",
                (
                    to_db(value.id),
                    to_db(value.enrollment.id),
                    to_db(value.captured_at),
                    to_db(value.progress_percentage),
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
            )
        )


class EvaluationRepository(_Repository):
    table = "evaluation"

    def save(self, value: Evaluation) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO evaluation VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                enrollment_id=excluded.enrollment_id,target_type=excluded.target_type,target_id=excluded.target_id,
                status=excluded.status,score=excluded.score,max_score=excluded.max_score,passed=excluded.passed,
                completed_at=excluded.completed_at""",
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
            )
        )


class CommunicationRecordRepository(_Repository):
    table = "communication_record"

    def save(self, value: CommunicationRecord) -> None:
        with connection(self.path) as db:
            db.execute(
                """INSERT INTO communication_record VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                enrollment_id=excluded.enrollment_id,communication_type=excluded.communication_type,reason=excluded.reason,
                suggested_at=excluded.suggested_at,status=excluded.status,reviewed_at=excluded.reviewed_at,
                sent_at=excluded.sent_at,deduplication_key=excluded.deduplication_key,context_key=excluded.context_key""",
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
                ),
            )

    def get(self, record_id: UUID) -> CommunicationRecord | None:
        row = self._row(record_id)
        if row is None:
            return None
        enrollment = EnrollmentRepository(self.path).get(UUID(row["enrollment_id"]))
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
            )
        )
