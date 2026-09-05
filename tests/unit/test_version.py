"""Tests for version availability."""

from adams_tutoria import __version__


def test_version_exists():
    """Verify __version__ exists and is a string."""
    assert hasattr(__version__, "__class__")
    assert isinstance(__version__, str)
    assert __version__ == "0.1.0"
