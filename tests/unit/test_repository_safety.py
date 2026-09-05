"""Lightweight checks for repository data-protection safeguards."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_operational_paths_are_ignored() -> None:
    """Verify representative local data and secret paths are ignored by Git."""
    paths = (
        "data/private/student-export.csv",
        "data/local/tutoria.sqlite3",
        "local.db",
        "local.db-journal",
        "local.db-shm",
        "local.db-wal",
        "local.sqlite-journal",
        "local.sqlite-shm",
        "local.sqlite-wal",
        "local.sqlite3-journal",
        "local.sqlite3-shm",
        "local.sqlite3-wal",
        ".env",
        ".env.local",
    )

    for path in paths:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", "--", path],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, f"Path is not ignored: {path}"


def test_repository_safety_documentation_exists() -> None:
    """Verify the README states the local-data policy and synthetic-fixture rule."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Operational data must stay local" in readme
    assert "synthetic data only" in readme
    assert "no environment variables" in readme
