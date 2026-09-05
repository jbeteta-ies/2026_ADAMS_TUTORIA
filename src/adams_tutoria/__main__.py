"""Entry point for the ADAMS Tutoria application."""

import sys


def main() -> int:
    """Print application banner and exit successfully."""
    print(f"ADAMS Tutoria v{__import__('adams_tutoria').__version__} — Python 3.13")
    return 0


if __name__ == "__main__":
    sys.exit(main())
