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
        # ``executescript`` issues an implicit COMMIT before executing its
        # script.  Migrations must be one unit: a rejected legacy catalog
        # must not leave newly-created tables behind.
        _reject_legacy_duplicates_if_present(db)
        for statement in SCHEMA.split(";"):
            if statement.strip():
                db.execute(statement)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(course)")}
        for name, definition in COURSE_ADDITIONS.items():
            if name not in columns:
                db.execute(f"ALTER TABLE course ADD COLUMN {name} {definition}")
        _migrate_catalog_state(db)
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
            "threshold": "TEXT",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE evaluation ADD COLUMN {name} {definition}")
        history_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(evaluation_history)")
        }
        if "threshold" not in history_columns:
            db.execute("ALTER TABLE evaluation_history ADD COLUMN threshold TEXT")
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
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_course_code "
            "ON course(code) WHERE code IS NOT NULL"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_edition_external "
            "ON edition(course_id, external_id) WHERE external_id IS NOT NULL"
        )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_edition_label "
            "ON edition(course_id, label) WHERE external_id IS NULL"
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


def _migrate_catalog_state(db: sqlite3.Connection) -> None:
    """Migrate legacy flags without selecting, deleting, or merging duplicates."""

    course_columns = {row["name"] for row in db.execute("PRAGMA table_info(course)")}
    edition_columns = {row["name"] for row in db.execute("PRAGMA table_info(edition)")}
    course_active = "active" if "active" in course_columns else "1"
    edition_active = "active" if "active" in edition_columns else "1"
    db.execute(
        f"INSERT OR IGNORE INTO course_state(course_id, active) "
        f"SELECT id, {course_active} FROM course"
    )
    db.execute(
        f"INSERT OR IGNORE INTO edition_state(edition_id, active) "
        f"SELECT id, {edition_active} FROM edition"
    )


def _reject_legacy_duplicates_if_present(db: sqlite3.Connection) -> None:
    tables = {
        row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "course" in tables and "edition" in tables:
        _reject_legacy_duplicates(db)


def _reject_legacy_duplicates(db: sqlite3.Connection) -> None:
    duplicate_course = db.execute(
        "SELECT code FROM course WHERE code IS NOT NULL GROUP BY code HAVING COUNT(*) > 1"
    ).fetchone()
    if duplicate_course is not None:
        raise ValueError(f"duplicate course code: {duplicate_course['code']}")
    duplicate_edition = db.execute(
        "SELECT course_id, external_id FROM edition WHERE external_id IS NOT NULL "
        "GROUP BY course_id, external_id HAVING COUNT(*) > 1"
    ).fetchone()
    if duplicate_edition is not None:
        raise ValueError("duplicate edition external_id")
    duplicate_label = db.execute(
        "SELECT course_id, label FROM edition WHERE external_id IS NULL "
        "GROUP BY course_id, label HAVING COUNT(*) > 1"
    ).fetchone()
    if duplicate_label is not None:
        raise ValueError("duplicate edition label")
