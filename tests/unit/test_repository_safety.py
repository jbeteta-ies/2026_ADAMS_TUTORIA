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
        "data/raw/adams-export.csv",
        "data/processed/generated-communication.txt",
        "data/private/adams_tutoria.sqlite3.bak",
        "data/local/adams_tutoria.sqlite3.backup",
        "data/local/adams_tutoria.sqlite3.dump",
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


def test_privacy_audit_documentation_covers_required_surfaces() -> None:
    """Keep the repository audit available alongside the implementation."""
    document = (ROOT / "docs" / "privacy-security-retention.md").read_text(encoding="utf-8")

    for required_section in (
        "Rutas y configuración",
        "SQLite",
        "Imports y exports",
        "Comunicaciones",
        "Logs y errores",
        "Backups",
        "Fixtures",
        "Retención",
    ):
        assert required_section in document


def test_tracked_fixture_files_are_explicitly_synthetic() -> None:
    """Tracked fixtures, when added, must identify themselves as synthetic."""
    fixtures = ROOT / "tests" / "fixtures"
    if not fixtures.exists():
        return

    for path in fixtures.rglob("*"):
        if path.is_file() and path.suffix.lower() in {
            ".csv",
            ".json",
            ".md",
            ".txt",
            ".yaml",
            ".yml",
        }:
            content = path.read_text(encoding="utf-8")
            assert "synthetic" in content.lower(), f"Fixture is not marked synthetic: {path}"
