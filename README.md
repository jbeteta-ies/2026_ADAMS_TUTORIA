# ADAMS Tutoria

Local application to support tutoring and monitoring of ADAMS online courses.

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/) (fast Python package installer and resolver)

## Setup

```bash
uv sync
```

This creates a local virtual environment (`.venv/`) and installs dependencies.

## Run

Preferred:

```bash
uv run adams-tutoria
```

Alternative:

```bash
uv run python -m adams_tutoria
```

Both commands print the application banner and exit.

### Streamlit dashboard

The initial dashboard shell uses only synthetic catalog options and does not
read SQLite, ADAMS exports, or any operational data. Start it with:

```bash
uv run streamlit run src/adams_tutoria/dashboard.py
```

The sidebar provides basic navigation and independent course/edition
selectors. Editions are filtered by the selected course. The current
selection is kept in Streamlit session state as `course_id` and `edition_id`.
The Edición page currently shows six deterministic metrics over a synthetic
demo provider: total enrollments, not started, inactive, pending evaluations,
completed, and cases requiring attention. It does not read SQLite, imports, or
ADAMS data; an enrollment can contribute to several reason metrics.

## Development

### Tests

```bash
uv run pytest
```

### Lint

```bash
uv run ruff check .
```

### Format check

```bash
uv run ruff format --check .
```

### Format write

```bash
uv run ruff format .
```

### Type check

```bash
uv run mypy src
```

## Configuration

The standard-library configuration layer is available through
`adams_tutoria.config`:

```python
from adams_tutoria.config import default_config, load_config

config = default_config()
# Or load documented ADAMS_TUTORIA_* overrides at call time:
config = load_config()
```

Defaults use `data/private/` and `data/local/` below the configured base
directory. Paths are only represented; configuration does not create
directories, access files, or initialize SQLite. `load_config` accepts an
optional `environ` mapping for deterministic callers (`environ={}` disables
all environment overrides). Relative values are joined to the base directory.

Supported overrides are:

- `ADAMS_TUTORIA_BASE_DIR`
- `ADAMS_TUTORIA_DATA_ROOT`
- `ADAMS_TUTORIA_PRIVATE_DATA_DIR`
- `ADAMS_TUTORIA_LOCAL_DATA_DIR`

Setting `ADAMS_TUTORIA_DATA_ROOT` changes the default root for the private and
local directories; an explicit child-directory override takes precedence.

## Local data and secrets

Operational data must stay local and must never be committed to GitHub. Use
`data/private/` or `data/local/` for local application data, including ADAMS
exports, imported reports, generated communications, and databases. The whole
`data/` directory is ignored by Git, as are SQLite/database files and local
`.env` configuration files.

Do not store credentials, session cookies, API keys, real student information,
or unredacted reports and exports in tracked files. Tests and examples must use
synthetic data only; versioned test fixtures belong under `tests/fixtures/`.

### SQLite persistence

The persistence layer is in `adams_tutoria.persistence` and uses only Python's
standard-library `sqlite3`. The operational database is explicitly initialized
at `AppConfig.local_data_dir/adams_tutoria.sqlite3` by calling
`initialize_database(database_path(config))`; importing the package never opens a
database. Persistence tests use only `tmp_path`, never the operational path, and
contain no real student data. This implementation uses no WAL mode, ORM, or
migrations. A future Issue may introduce versioned migrations if the schema must
evolve.

No `.env` loader is used. Do not add real secret values to environment examples
or tracked files. There are no environment variables read at import time.

## Domain model

The standard-library domain model defines seven frozen entities in
`adams_tutoria.domain`:

- `Course(id, name, code=None, description=None, content_source=None)` is a reusable course
  definition. Its UUID identity is supplied by the caller.
- `ContentSource(source_type, location, subpath=None, revision=None)` is an
  optional per-course reference. `source_type` is `local_path` or `repository`.
  The metadata is stored only as a reference; this application does not clone,
  synchronize, index, or search the referenced content.
- `Edition(id, course, label, external_id=None, start_date=None, end_date=None)`
  is one concrete edition and keeps a direct reference to its `Course`.
- `Student(id, full_name, email=None, external_id=None)` represents a student's
  identity independently of any course edition.
- `Enrollment(id, student, edition, external_id=None)` represents one
  student's membership in one concrete `Edition` and keeps references to both
  its `Student` and its `Edition`.
- `ProgressSnapshot(id, enrollment, captured_at, progress_percentage,
  external_id=None)` records one observation. Multiple snapshots may exist for
  one enrollment.
  `progress_percentage` is a `Decimal` in the inclusive range 0 through 100,
  and `captured_at` must be timezone-aware.
- `Evaluation(id, enrollment, target_type, target_id, status=PENDING,
  score=None, max_score=None, passed=None, completed_at=None,
  target_label=None, external_id=None)` represents an evaluation at
  either `MODULE` or `ACTIVITY` level. `PENDING` cannot contain result data or
  a completion time; `COMPLETED` may have no result data. A score may exist
  without a maximum, a maximum requires a score, and a score cannot exceed its
  maximum. Scores use `Decimal` and have no assumed scale. `passed` is an
  explicit optional boolean and is never derived from the score; `completed_at`,
  when present, must be timezone-aware.
- `CommunicationRecord(id, enrollment, communication_type, reason, suggested_at,
  status=SUGGESTED, reviewed_at=None, sent_at=None, deduplication_key,
  context_key=None)` records communication history. Type and reason are
  structured string codes, not enums or free-text notes. Timestamps are
  timezone-aware; approval/discard require human review and sent records
  require both review and send timestamps. The recipient is the `Enrollment`,
  without duplicating student identity.

Several editions may reference the same course. The model is generic and does
not depend on a particular ADAMS course or external platform. A single
`Student` can be reused in multiple `Enrollment` records for different
`Edition` instances, avoiding unnecessary duplication of identity data.
Required text fields cannot be blank, and an edition cannot end before it
starts. ADAMS report details remain uncertain until real report samples can be
reviewed; in particular, the relationship between this percentage and the
ADAMS scale, target identifier mapping, score scale, and passing rules is not
established by this model. There are
deliberately no `Module` or `Activity` entities, SCORM fields, attempt counts,
additional evaluation statuses, persistence, or import logic. All of those
 remain outside this model.

### Communication history limits

The record stores a caller-provided deduplication key and optional context key,
but does not calculate keys, query duplicates, or enforce persistence
uniqueness; historical records may share keys. It does not recommend, generate
or contain message text, templates, or an ADAMS connector/send method. Human
review is required and sending remains manual copy/paste into ADAMS. These
boundaries prepare the model for future Issues #18–#21 (recommendation,
deduplication, generation, and manual workflow) without implementing them now.

### Import contract

The source-independent import boundary is documented in
[`docs/import-contract.md`](docs/import-contract.md). It defines typed
candidate records, evidence rules, safe diagnostics, partial-success results,
and the `ImportAdapter` protocol without implementing source parsing.
