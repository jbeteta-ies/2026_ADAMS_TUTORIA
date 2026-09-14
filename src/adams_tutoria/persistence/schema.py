"""The SQLite schema and additive compatibility statements."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS course (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT, description TEXT,
    content_source_type TEXT, content_source_location TEXT,
    content_source_subpath TEXT, content_source_revision TEXT
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
CREATE TABLE IF NOT EXISTS content_node (
    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES course(id),
    edition_id TEXT NOT NULL REFERENCES edition(id), node_type TEXT NOT NULL,
    title TEXT NOT NULL, parent_id TEXT REFERENCES content_node(id), external_id TEXT
);
CREATE TABLE IF NOT EXISTS content_progress_snapshot (
    id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL REFERENCES enrollment(id),
    node_id TEXT NOT NULL REFERENCES content_node(id), captured_at TEXT NOT NULL,
    progress_percentage TEXT NOT NULL, external_id TEXT
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
    context_key TEXT,
    recommendation_id TEXT,
    trigger TEXT,
    edition_id TEXT,
    postponed_at TEXT,
    copied_at TEXT
);
CREATE TABLE IF NOT EXISTS tutor_action (
    id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL REFERENCES enrollment(id),
    occurred_at TEXT NOT NULL, action TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS import_batch (
    id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_name TEXT NOT NULL,
    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
    source_reference TEXT, source_fingerprint TEXT, context TEXT, action TEXT, group_name TEXT,
    total_count INTEGER NOT NULL DEFAULT 0, accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0, warning_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS import_batch_change (
    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES import_batch(id),
    entity_type TEXT NOT NULL, change_type TEXT NOT NULL, entity_id TEXT,
    source_row_number INTEGER, source_identifier TEXT, diagnostic_code TEXT,
    diagnostic_message TEXT
);
CREATE TABLE IF NOT EXISTS student_external_identity (
    source TEXT NOT NULL, context TEXT NOT NULL, source_student_id TEXT NOT NULL,
    student_id TEXT NOT NULL REFERENCES student(id),
    PRIMARY KEY (source, context, source_student_id)
);
CREATE TABLE IF NOT EXISTS enrollment_external_identity (
    source TEXT NOT NULL, context TEXT NOT NULL, source_enrollment_id TEXT NOT NULL,
    edition_id TEXT NOT NULL REFERENCES edition(id),
    enrollment_id TEXT NOT NULL REFERENCES enrollment(id),
    PRIMARY KEY (source, context, source_enrollment_id, edition_id)
);
CREATE TABLE IF NOT EXISTS enrollment_state (
    enrollment_id TEXT PRIMARY KEY REFERENCES enrollment(id), active INTEGER NOT NULL,
    changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS student_history (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES student(id),
    batch_id TEXT NOT NULL REFERENCES import_batch(id),
    event_type TEXT NOT NULL, full_name TEXT, email TEXT, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollment_history (
    id TEXT PRIMARY KEY, enrollment_id TEXT NOT NULL REFERENCES enrollment(id),
    batch_id TEXT NOT NULL REFERENCES import_batch(id),
    event_type TEXT NOT NULL, active INTEGER NOT NULL, external_id TEXT,
    occurred_at TEXT NOT NULL
);
"""

COURSE_ADDITIONS = {
    "content_source_type": "TEXT",
    "content_source_location": "TEXT",
    "content_source_subpath": "TEXT",
    "content_source_revision": "TEXT",
}

COMMUNICATION_RECORD_ADDITIONS = {
    "recommendation_id": "TEXT",
    "trigger": "TEXT",
    "edition_id": "TEXT",
    "postponed_at": "TEXT",
    "copied_at": "TEXT",
}

IMPORT_BATCH_ADDITIONS = {
    "scope_type": "TEXT NOT NULL DEFAULT 'partial'",
    "scope_reference": "TEXT",
    "idempotency_key": "TEXT",
}
