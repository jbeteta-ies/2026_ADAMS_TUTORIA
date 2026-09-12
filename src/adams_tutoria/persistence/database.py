"""SQLite connection and explicit schema initialization."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from adams_tutoria.config import AppConfig

from .schema import COMMUNICATION_RECORD_ADDITIONS, COURSE_ADDITIONS, SCHEMA

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
            "CREATE INDEX IF NOT EXISTS idx_import_batch_change_batch "
            "ON import_batch_change(batch_id, id)"
        )
