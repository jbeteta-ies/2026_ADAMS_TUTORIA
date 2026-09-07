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

No `.env` loader is used. Do not add real secret values to environment examples
or tracked files. There are no environment variables read at import time.

## Domain model

The standard-library domain model defines six frozen entities in
`adams_tutoria.domain`:

- `Course(id, name, code=None, description=None)` is a reusable course
  definition. Its UUID identity is supplied by the caller.
- `Edition(id, course, label, external_id=None, start_date=None, end_date=None)`
  is one concrete edition and keeps a direct reference to its `Course`.
- `Student(id, full_name, email=None, external_id=None)` represents a student's
  identity independently of any course edition.
- `Enrollment(id, student, edition, external_id=None)` represents one
  student's membership in one concrete `Edition` and keeps references to both
  its `Student` and its `Edition`.
- `ProgressSnapshot(id, enrollment, captured_at, progress_percentage)` records
  one observation. Multiple snapshots may exist for one enrollment.
  `progress_percentage` is a `Decimal` in the inclusive range 0 through 100,
  and `captured_at` must be timezone-aware.
- `Evaluation(id, enrollment, target_type, target_id, status=PENDING,
  score=None, max_score=None, passed=None, completed_at=None)` represents an evaluation at
  either `MODULE` or `ACTIVITY` level. `PENDING` cannot contain result data or
  a completion time; `COMPLETED` may have no result data. A score may exist
  without a maximum, a maximum requires a score, and a score cannot exceed its
  maximum. Scores use `Decimal` and have no assumed scale. `passed` is an
  explicit optional boolean and is never derived from the score; `completed_at`,
  when present, must be timezone-aware.

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
