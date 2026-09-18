"""SQLite connection and explicit schema initialization."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from adams_tutoria.config import AppConfig

from .schema import (
    COMMUNICATION_RECORD_ADDITIONS,
    COURSE_ADDITIONS,
    IMPORT_BATCH_ADDITIONS,
    SCHEMA,
)

DATABASE_FILENAME = "adams_tutoria.sqlite3"


def database_path(config: AppConfig) -> Path:
    """Return the operational database path below the configured local directory."""

    return config.local_data_dir / DATABASE_FILENAME


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a transaction, committing on success and rolling back on failure."""

    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
    except BaseException:
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.close()


def initialize_database(path: Path) -> None:
    """Create all persistence tables, idempotently, without running at import time."""

    with connection(path) as db:
        db.executescript(SCHEMA)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(course)")}
        for name, definition in COURSE_ADDITIONS.items():
            if name not in columns:
                db.execute(f"ALTER TABLE course ADD COLUMN {name} {definition}")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(communication_record)")}
        for name, definition in COMMUNICATION_RECORD_ADDITIONS.items():
            if name not in columns:
                db.execute(f"ALTER TABLE communication_record ADD COLUMN {name} {definition}")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_communication_record_enrollment_time "
            "ON communication_record(enrollment_id, suggested_at)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_communication_record_edition_time "
            "ON communication_record(edition_id, suggested_at)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tutor_action_enrollment_time "
            "ON tutor_action(enrollment_id, occurred_at)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_node_edition ON content_node(edition_id, id)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_snapshot_scope "
            "ON content_progress_snapshot(enrollment_id, node_id, captured_at)"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_content_snapshot_observation "
            "ON content_progress_snapshot(enrollment_id, node_id, captured_at, progress_percentage)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_import_batch_change_batch "
            "ON import_batch_change(batch_id, id)"
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(import_batch)")}
        for name, definition in IMPORT_BATCH_ADDITIONS.items():
            if name not in columns:
                db.execute(f"ALTER TABLE import_batch ADD COLUMN {name} {definition}")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(import_batch)")}
        if "excluded_count" not in columns:
            db.execute(
                "ALTER TABLE import_batch ADD COLUMN excluded_count INTEGER NOT NULL DEFAULT 0"
            )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(evaluation)")}
        for name, definition in {
            "result_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "raw_value": "TEXT",
            "numeric_value": "TEXT",
            "scale": "TEXT",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE evaluation ADD COLUMN {name} {definition}")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(generation_record)")}
        for name, definition in {
            "draft_text": "TEXT",
            "model_name": "TEXT NOT NULL DEFAULT 'unknown'",
            "prompt_version": "TEXT NOT NULL DEFAULT 'unknown'",
            "draft_hash": "TEXT",
            "draft_ref": "TEXT",
            "error_code": "TEXT",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE generation_record ADD COLUMN {name} {definition}")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_import_batch_idempotency "
            "ON import_batch(idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_student_external_identity_student "
            "ON student_external_identity(student_id)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_generation_record_created "
            "ON generation_record(created_at)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_generation_transition_generation "
            "ON generation_transition(generation_id, occurred_at, id)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_generation_failure_enrollment_time "
            "ON generation_failure(enrollment_id, occurred_at, id)"
        )
