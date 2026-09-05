"""Tests for main entry point behavior."""

import subprocess
import sys

from adams_tutoria.__main__ import main


def test_main_returns_zero():
    """Verify main() returns exit code 0."""
    assert main() == 0


def test_main_prints_banner(capsys):
    """Verify main() prints the application banner."""
    main()
    captured = capsys.readouterr()
    assert "ADAMS Tutoria v0.1.0" in captured.out
    assert "Python 3.13" in captured.out


def test_cli_execution():
    """Verify the CLI command executes successfully with exit code 0."""
    result = subprocess.run(
        [sys.executable, "-m", "adams_tutoria"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ADAMS Tutoria v0.1.0" in result.stdout
    assert "Python 3.13" in result.stdout


def test_cli_via_uv_run():
    """Verify the uv run adams-tutoria command executes successfully."""
    result = subprocess.run(
        ["uv", "run", "adams-tutoria"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "ADAMS Tutoria v0.1.0" in result.stdout
    assert "Python 3.13" in result.stdout
