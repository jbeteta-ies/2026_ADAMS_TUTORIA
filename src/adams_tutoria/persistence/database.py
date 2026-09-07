"""SQLite connection and explicit schema initialization."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from adams_tutoria.config import AppConfig

from .schema import SCHEMA

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
