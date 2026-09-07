"""Explicit SQLite persistence for the domain model."""

from .database import connection, database_path, initialize_database
from .repositories import (
    CommunicationRecordRepository,
    CourseRepository,
    EditionRepository,
    EnrollmentRepository,
    EvaluationRepository,
    ProgressSnapshotRepository,
    StudentRepository,
)

__all__ = [
    "CommunicationRecordRepository",
    "CourseRepository",
    "EditionRepository",
    "EnrollmentRepository",
    "EvaluationRepository",
    "ProgressSnapshotRepository",
    "StudentRepository",
    "connection",
    "database_path",
    "initialize_database",
]
