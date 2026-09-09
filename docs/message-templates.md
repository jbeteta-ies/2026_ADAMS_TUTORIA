# Message templates

`adams_tutoria.message_templates` provides a small, standard-library-only
renderer for the six identifiers in Issue #18's `COMMUNICATION_CATALOG`.

The renderer accepts the immutable `MessageContext` fields `name`, `course`,
`edition`, and `context`. Templates use only explicit `{{variable}}` tokens;
unknown names, malformed tokens, missing context values, and blank tones fail
strictly. The result never contains unresolved placeholders.

Template definitions and contexts are frozen and rendering has no side effects.
Variant selection uses SHA-256 over the identifier, tone, and context, so the
same inputs always produce the same result without randomness or persistence.
Each catalog type has multiple natural-language variants. Tone remains the
descriptive string metadata established by Issue #18; this module does not
create a second tone catalog or reinterpret tone values.

This feature does not send messages, access ADAMS, use SQLite, provide a UI,
call an LLM, or recommend communications.
