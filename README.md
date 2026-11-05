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

For the complete local installation and operation procedure, including the
dashboard, generic imports, manual communications, local data, backups, and
known limitations, see [`docs/installation-and-operation.md`](docs/installation-and-operation.md).

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

The dashboard reads courses, editions, enrollments, progress, evaluations and
communication history from the local SQLite operational store. It is read-only
for those domain records and never seeds profiles or synthetic data. Start it
with:

```bash
uv run streamlit run src/adams_tutoria/dashboard.py
```

The sidebar provides independent persisted course/edition selectors. Empty and
archived selections are shown without creating replacement records. The
Edición page separates progress from evaluation status and consumes the
existing follow-up and recommendation contracts. Ollama is optional and
loopback-only; generation requires an explicitly selected available model,
shows a minimized operational context, and always requires human review.

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

### Local sites YAML

`config.yaml.example` documents the ignored local `config.yaml` contract. Copy
the example locally and replace only its placeholders; no credentials or
cookies belong in tracked files. `adams_tutoria.config.load_sites_config(path)`
uses `yaml.safe_load` and returns frozen typed records. The schema requires
`schema_version: 1`, a non-empty list of sites, and unique `id` values.

Each site requires `id`, `provider`, `login_url`, `target_url`, `username`, and
`password`. Optional dates use `YYYY-MM-DD`; `weekdays` defaults to every day;
times default to `00:00`–`23:59:59`; `timezone` defaults to `UTC` and must be an
IANA timezone; `interval_seconds` defaults to 300 and must be positive; and
`log_file` defaults to a relative `data/local/logs/<id>.log` path. URLs must be
HTTP(S) URLs without embedded credentials. Unknown fields, unsafe log paths,
duplicate IDs, invalid dates/times, and invalid timezones are rejected without
including password values in errors.

After copying `config.yaml.example` to the ignored local `config.yaml`, run the
continuous monitor with:

```bash
uv run adams-monitor
```

Para un worker independiente, selecciona el sitio y limita la ejecución a una
sola ventana:

```bash
uv run adams-monitor --config config.yaml --site synthetic-site --once-window
```

`--once-window` requiere siempre `--site`; usarlo sin sitio devuelve el error
de configuración `2` antes de iniciar la monitorización.

`--site` inexistente, un YAML ausente o inválido devuelve `2` sin mostrar
secretos; un fallo de ejecución devuelve `1`; una terminación normal o por
`SIGINT`/`SIGTERM` devuelve `0`. El worker espera antes de la ventana, respeta
ventanas nocturnas y no inicia una segunda ventana.

The command validates configuration before starting Playwright and coordinates
the scheduler, monitor, provider adapters, and independent site logs. SIGINT,
SIGTERM, and Ctrl-C request a cooperative clean shutdown. Exit status 2 means
configuration could not be loaded or validated, 1 means an execution failure,
and 0 means a clean stop. Sessions and browser resources are closed
best-effort and idempotently; site-level failures remain isolated by
`MultiSiteMonitor`.

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

### Local generation contract

`GenerationRecord` links a draft to an `Enrollment` and communication type.
Its states are `GENERATED`, `REVIEWED`, `EDITED`, `COPIED`, `DISCARDED`, and
`SENT`. `SENT` is only a manual external-send mark after copying; it never
invokes ADAMS, SMTP, a model, or another external channel. SQLite stores only
the minimized allowlisted payload and draft text. Student identity, credentials,
sessions, raw exports, and full database records are prohibited from the model
payload. Records can be explicitly deleted; operational databases remain local
and ignored. See [`docs/local-generation-contract.md`](docs/local-generation-contract.md).

### SQLite persistence

The persistence layer is in `adams_tutoria.persistence` and uses only Python's
standard-library `sqlite3`. The operational database is explicitly initialized
at `AppConfig.local_data_dir/adams_tutoria.sqlite3` by calling
`initialize_database(database_path(config))`; importing the package never opens a
database. Persistence tests use only `tmp_path`, never the operational path, and
contain no real student data. This implementation uses no WAL mode, ORM, or
migrations. A future Issue may introduce versioned migrations if the schema must
evolve.

No automatic `.env` loader is used. The login prototype reads a `.env` only when
the CLI runs. There are no environment variables read at import time. Do not
add real secret values to environment examples or tracked files.

### ADAMS login prototype

Create `.env` locally by copying `.env.example` and replacing its placeholders.
`.env` is ignored by Git and must never be versioned, committed, or shared; only
`.env.example` is versioned. Do not create or populate `.env` in a pull request.
Install the browser with `uv run playwright install chromium`, then call
`login_with_playwright` from `adams_tutoria.adams_login`. The prototype opens
one ephemeral browser context, submits only the login form, reports success,
failure, or CAPTCHA/MFA blocking, and closes the context without persisting a
session. The detector supports the current ADAMS login markup (`nombre`,
`clave`, and a `Submit` button, including when that button is outside a form
container). `ADAMS_TARGET_URL` and `ADAMS_INTERVAL_SECONDS` are reserved for
later Issues and are not used by this prototype.

Run one login attempt from the command line with:

```bash
uv run adams-login
```

The command is deliberately **one-shot**: it makes one login attempt, closes
its ephemeral browser context, prints exactly one safe status, and exits. It
does not reload pages, retry, poll, monitor ADAMS, read course content, send
communications, or persist a session. Existing environment variables take
precedence over `.env`; configuration, browser, and unconfirmed-login errors
are `failed`, while CAPTCHA, MFA, or required user intervention is `blocked`.
The latter stops the attempt without any bypass. No login logs are produced by
this CLI; logging is reserved for a later Issue.

## Domain model

The standard-library domain model defines seven frozen entities in
`adams_tutoria.domain`:

- `Course(id, name, code=None, description=None, content_source=None)` is a reusable course
  definition. Its UUID identity is supplied by the caller.
- `ContentSource(source_type, location, subpath=None, revision=None)` is an
  optional per-course reference. `source_type` is `local_path` or `repository`.
  The metadata is stored as a reference. Local Markdown indexing and search
  are documented in [`docs/content-search.md`](docs/content-search.md).
  Repository sources are treated only as already available local checkouts;
  no cloning or synchronization is performed.
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
- `ContentNode(id, course, edition, node_type, title, parent=None,
  external_id=None)` models only an explicitly supplied hierarchy. `node_type`
  is `MODULE`, `SUBMODULE`, or `ELEMENT`; the latter two require the
  corresponding parent level. The node's `Course` and `Edition` are validated
  and must agree, but are never created by node persistence.
- `ContentProgressSnapshot(id, enrollment, node, captured_at,
  progress_percentage, external_id=None)` records dated, append-only progress
  observations for one enrollment and node. Its percentage is a finite
  `Decimal` from 0 through 100. It is separate from `Evaluation`.
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

### Import batches

Import execution metadata is persisted as `ImportBatch` and
`ImportBatchChange`. Only safe provenance, counters, statuses, timestamps, and
compact diagnostics are stored; complete files, raw rows, and unnecessary PII
remain outside the database. Enrollment upserts, logical deactivation, explicit
reactivation, and append-only lifecycle history are implemented; see
[`docs/enrollment-lifecycle.md`](docs/enrollment-lifecycle.md). Excel parsing,
UI, OCR, and ADAMS connectors are intentionally out of scope.

### Import contract

The source-independent import boundary is documented in
[`docs/import-contract.md`](docs/import-contract.md). It defines typed
candidate records, evidence rules, safe diagnostics, partial-success results,
and the `ImportAdapter` protocol without implementing source parsing. The
common operation pipeline also accepts non-file adapters; the synthetic
`InMemoryImportAdapter` example reaches the same preview and explicit
confirmation boundary as Excel without coupling persistence or UI to a
workbook.
