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

## Status

No business logic implemented yet. This is the initial project structure only.