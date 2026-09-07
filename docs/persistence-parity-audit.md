# SQLite persistence parity audit

This audit was performed against the current `domain.py`. `ProgressSnapshot`
does not currently define `external_id`; `Evaluation` does not currently define
`target_label` or `external_id`, so those fields are intentionally not added by
Issue #9.

| Entity | Dataclass fields | Schema columns | Write mapping | Read mapping / constructor | Round-trip test |
| --- | --- | --- | --- | --- | --- |
| Course | `id`, `name`, `code`, `description` | all four | `CourseRepository.save` | `CourseRepository.get` → `Course(...)` | `test_all_entities_round_trip_every_field_and_relationship` |
| Edition | `id`, `course`, `label`, `external_id`, `start_date`, `end_date` | `id`, `course_id`, `label`, `external_id`, `start_date`, `end_date` | `EditionRepository.save` | course lookup + `Edition(...)` | same |
| Student | `id`, `full_name`, `email`, `external_id` | all four | `StudentRepository.save` | `StudentRepository.get` → `Student(...)` | same |
| Enrollment | `id`, `student`, `edition`, `external_id` | `id`, `student_id`, `edition_id`, `external_id` | `EnrollmentRepository.save` | relationship lookups + `Enrollment(...)` | same |
| ProgressSnapshot | `id`, `enrollment`, `captured_at`, `progress_percentage` | `id`, `enrollment_id`, `captured_at`, `progress_percentage` | `ProgressSnapshotRepository.save` | relationship lookup + `ProgressSnapshot(...)` | same; duplicate test |
| Evaluation | `id`, `enrollment`, `target_type`, `target_id`, `status`, `score`, `max_score`, `passed`, `completed_at` | all nine, with optional values nullable | `EvaluationRepository.save` | enum/scalar conversions + `Evaluation(...)` | same; optional-None and upsert tests |
| CommunicationRecord | `id`, `enrollment`, `communication_type`, `reason`, `suggested_at`, `status`, `reviewed_at`, `sent_at`, `deduplication_key`, `context_key` | all ten, with optional timestamps/context nullable | `CommunicationRecordRepository.save` | enum/scalar conversions + `CommunicationRecord(...)` | same; upsert test |

Scalar parity is explicit: UUIDs are text, dates/datetimes are ISO text,
`Decimal` values are text, booleans are integer 0/1, enums use `.value`, and
optional values use SQL `NULL`. Every reconstruction uses a domain constructor;
no partial domain objects are created.
