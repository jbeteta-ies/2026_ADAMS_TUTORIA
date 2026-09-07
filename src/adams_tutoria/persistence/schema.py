"""The complete, deliberately small SQLite schema for Issue #9."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS course (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT, description TEXT
);
CREATE TABLE IF NOT EXISTS edition (
    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES course(id), label TEXT NOT NULL,
    external_id TEXT, start_date TEXT, end_date TEXT
);
CREATE TABLE IF NOT EXISTS student (
    id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT, external_id TEXT
);
CREATE TABLE IF NOT EXISTS enrollment (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES student(id),
    edition_id TEXT NOT NULL REFERENCES edition(id), external_id TEXT
);
CREATE TABLE IF NOT EXISTS progress_snapshot (
    id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL REFERENCES enrollment(id),
    captured_at TEXT NOT NULL, progress_percentage TEXT NOT NULL, external_id TEXT
);
CREATE TABLE IF NOT EXISTS evaluation (
    id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL REFERENCES enrollment(id),
    target_type TEXT NOT NULL, target_id TEXT NOT NULL, status TEXT NOT NULL,
    score TEXT, max_score TEXT, passed INTEGER, completed_at TEXT,
    target_label TEXT, external_id TEXT
);
CREATE TABLE IF NOT EXISTS communication_record (
    id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL REFERENCES enrollment(id),
    communication_type TEXT NOT NULL, reason TEXT NOT NULL, suggested_at TEXT NOT NULL,
    status TEXT NOT NULL, reviewed_at TEXT, sent_at TEXT, deduplication_key TEXT NOT NULL,
    context_key TEXT
);
"""
