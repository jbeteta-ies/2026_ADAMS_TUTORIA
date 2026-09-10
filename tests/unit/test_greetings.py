"""Tests for greeting helpers."""

from adams_tutoria.greetings import saludar


def test_saludar_with_name() -> None:
    """A named person receives the expected greeting."""
    assert saludar("Ana") == "Hola, Ana"


def test_saludar_preserves_name_text() -> None:
    """The function preserves the supplied name text exactly."""
    assert saludar("equipo de tutoría") == "Hola, equipo de tutoría"
