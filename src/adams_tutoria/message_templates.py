"""Deterministic, local rendering of reusable communication templates.

This module only renders text.  It does not recommend, persist, send, or
interpret communications.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from adams_tutoria.communication_catalog import COMMUNICATION_CATALOG

_PLACEHOLDER: Final = re.compile(r"\{\{([^{}]*)\}\}")
_VARIABLE_NAME: Final = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED_VARIABLES: Final = frozenset({"name", "course", "edition", "context"})


def _validate_template(template: str) -> None:
    matches = tuple(_PLACEHOLDER.finditer(template))
    for match in matches:
        variable = match.group(1)
        if not _VARIABLE_NAME.fullmatch(variable) or variable not in _ALLOWED_VARIABLES:
            raise ValueError(f"unknown or invalid template variable: {variable!r}")
    remainder = _PLACEHOLDER.sub("", template)
    if any(character in remainder for character in "{}"):
        raise ValueError("template contains malformed placeholder syntax")


@dataclass(frozen=True, slots=True)
class MessageContext:
    """Immutable synthetic or caller-provided values for one rendering."""

    name: str
    course: str
    edition: str
    context: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in self.values()):
            raise ValueError("message context values must be non-blank strings")

    def values(self) -> tuple[str, ...]:
        return (self.name, self.course, self.edition, self.context)

    def as_mapping(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                "name": self.name,
                "course": self.course,
                "edition": self.edition,
                "context": self.context,
            }
        )


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    """Immutable variants for one of the communication catalog identifiers."""

    identifier: str
    variants: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.variants or any(
            not isinstance(item, str) or not item for item in self.variants
        ):
            raise ValueError("a template definition needs non-empty variants")
        for variant in self.variants:
            _validate_template(variant)


TEMPLATE_DEFINITIONS: Final[tuple[TemplateDefinition, ...]] = (
    TemplateDefinition(
        "invitation_to_start",
        (
            "Hola, {{name}}. Te damos la bienvenida a {{course}} ({{edition}}). "
            "Cuando te venga bien, puedes comenzar; {{context}}.",
            "Hola, {{name}}: {{course}} de {{edition}} ya está listo para ti. "
            "Un primer paso breve puede ser suficiente hoy; {{context}}.",
        ),
    ),
    TemplateDefinition(
        "inactivity_reminder",
        (
            "Hola, {{name}}. Hemos echado de menos tu avance en {{course}} ({{edition}}). "
            "{{context}}; retomar con calma también cuenta.",
            "Hola, {{name}}: si te apetece volver a {{course}}, puedes continuar desde "
            "{{context}} en {{edition}}. Estamos a tiempo.",
        ),
    ),
    TemplateDefinition(
        "pending_evaluation_reminder",
        (
            "Hola, {{name}}. La evaluación pendiente de {{course}} ({{edition}}) sigue "
            "disponible. {{context}}.",
            "Hola, {{name}}: cuando puedas, revisa la evaluación de {{course}} en "
            "{{edition}}. {{context}}.",
        ),
    ),
    TemplateDefinition(
        "passed_evaluation_congratulation",
        (
            "Enhorabuena, {{name}}: has superado la evaluación de {{course}} "
            "({{edition}}). {{context}}.",
            "¡Muy buen trabajo, {{name}}! Tu resultado en {{course}}, {{edition}}, "
            "refleja tu esfuerzo. {{context}}.",
        ),
    ),
    TemplateDefinition(
        "insufficient_result_encouragement",
        (
            "Hola, {{name}}. Un resultado insuficiente en {{course}} ({{edition}}) no "
            "define tu progreso. {{context}}.",
            "Ánimo, {{name}}: puedes revisar la evaluación de {{course}} en {{edition}} "
            "y volver a intentarlo. {{context}}.",
        ),
    ),
    TemplateDefinition(
        "completion_congratulation",
        (
            "Enhorabuena, {{name}}: has completado {{course}} en la edición "
            "{{edition}}. {{context}}.",
            "¡Felicidades, {{name}}! Terminar {{course}} ({{edition}}) es un logro "
            "importante. {{context}}.",
        ),
    ),
)

_TEMPLATES: Final[Mapping[str, TemplateDefinition]] = MappingProxyType(
    {definition.identifier: definition for definition in TEMPLATE_DEFINITIONS}
)


def render_message(
    identifier: str,
    context: MessageContext,
    *,
    tone: str | None = None,
) -> str:
    """Render one deterministic variant for a catalog communication type.

    Tone follows Issue #18's contract: it is descriptive string metadata, not
    an internally invented enum.  Blank or non-string values are rejected.
    """

    communication_type = COMMUNICATION_CATALOG.get(identifier)
    definition = _TEMPLATES.get(identifier)
    if definition is None:
        raise ValueError(f"no templates defined for communication type: {identifier}")
    selected_tone = communication_type.tone if tone is None else tone
    if not isinstance(selected_tone, str) or not selected_tone.strip():
        raise ValueError("tone must be a non-blank string")

    seed = "\x1f".join((identifier, selected_tone, *context.values()))
    index = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest(), "big") % len(
        definition.variants
    )
    values = context.as_mapping()
    rendered = _PLACEHOLDER.sub(lambda match: values[match.group(1)], definition.variants[index])
    if _PLACEHOLDER.search(rendered) or "{{" in rendered or "}}" in rendered:
        raise ValueError("rendered message contains an unresolved placeholder")
    return rendered
