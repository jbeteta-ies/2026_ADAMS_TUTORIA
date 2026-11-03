"""One-shot command-line entry point for the ADAMS login prototype."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from adams_tutoria.adams_login import AdamsLoginSettings, login_with_playwright

_STATUSES = {"success", "failed", "blocked"}


def main() -> int:
    """Load local configuration, make one login attempt, and print only its status."""
    # Configuration loading is intentionally restricted to CLI execution.
    load_dotenv(dotenv_path=Path(".env"), override=False)
    try:
        result = login_with_playwright(AdamsLoginSettings.from_environment())
        status = result.status if result.status in _STATUSES else "failed"
    except Exception:
        status = "failed"
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
