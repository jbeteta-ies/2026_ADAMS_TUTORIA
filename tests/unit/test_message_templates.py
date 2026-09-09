"""Tests for deterministic, synthetic message rendering."""

from dataclasses import FrozenInstanceError

import pytest

from adams_tutoria.communication_catalog import COMMUNICATION_CATALOG
from adams_tutoria.message_templates import (
    TEMPLATE_DEFINITIONS,
    MessageContext,
    TemplateDefinition,
    render_message,
)

CONTEXT = MessageContext("Alumno 001", "Curso sintético", "Edición 2026-A", "el módulo 2")


def test_all_catalog_types_render_with_context_and_no_placeholders() -> None:
    for communication_type in COMMUNICATION_CATALOG.types:
        identifier = communication_type.identifier
        rendered = render_message(identifier, CONTEXT)
        assert "Alumno 001" in rendered
        assert "{{" not in rendered
        assert "}}" not in rendered


def test_selection_is_deterministic_and_variants_differ() -> None:
    assert render_message("completion_congratulation", CONTEXT) == render_message(
        "completion_congratulation", CONTEXT
    )
    assert all(len(definition.variants) >= 2 for definition in TEMPLATE_DEFINITIONS)


def test_context_and_unknown_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="context"):
        MessageContext("", "Curso", "Edición", "contexto")
    with pytest.raises(KeyError, match="unknown communication type"):
        render_message("not_a_type", CONTEXT)
    with pytest.raises(ValueError, match="tone"):
        render_message("completion_congratulation", CONTEXT, tone=" ")


@pytest.mark.parametrize("variant", ["{{name}}}", "{{{name}}}", "{name}", "name}", "{name"])
def test_malformed_placeholder_braces_are_rejected(variant: str) -> None:
    with pytest.raises(ValueError, match="malformed"):
        TemplateDefinition("synthetic", (variant,))


def test_unknown_template_variable_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown or invalid"):
        TemplateDefinition("synthetic", ("Hola, {{nickname}}.",))


def test_template_definition_is_immutable() -> None:
    definition = TEMPLATE_DEFINITIONS[0]
    with pytest.raises(FrozenInstanceError):
        definition.identifier = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        definition.variants[0] = "other"  # type: ignore[index]


def test_tone_affects_deterministic_variant_selection() -> None:
    tones = ("neutral", "warm", "formal", "encouraging", "direct")
    rendered_by_tone = {
        tone: render_message("completion_congratulation", CONTEXT, tone=tone) for tone in tones
    }

    assert len(set(rendered_by_tone.values())) > 1
    assert rendered_by_tone["warm"] == render_message(
        "completion_congratulation", CONTEXT, tone="warm"
    )


def test_context_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        CONTEXT.name = "Otro"  # type: ignore[misc]
