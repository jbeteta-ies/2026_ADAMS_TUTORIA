# Recomendaciones de comunicación

`communication_recommendations` conecta `FollowUpAssessment`,
`EnrollmentSummary` y `AttentionCase` sin volver a calcular ninguna regla.
Los disparadores se configuran explícitamente a identificadores de
`COMMUNICATION_CATALOG`; el catálogo es la única fuente de tipos.

La función `recommend_communications` es pura y devuelve DTOs inmutables. Usa
un puerto de historial de solo lectura, una política configurable de repetición
y una identidad determinista por matrícula, edición, tipo y disparador. El
historial puede suprimir recomendaciones repetidas, pero nunca se escribe desde
este módulo. La prioridad se hereda del `AttentionCase` y no se recalcula.

Solo se usan señales semánticas explícitas: razones de seguimiento y resultados
`passed=True`/`False`. No se infieren resultados desde puntuaciones. Si falta
información o configuración para una señal, no se genera una recomendación.
La generación es dirigida por casos: cada recomendación requiere un
`AttentionCase` aplicable para la misma matrícula y edición que el resumen;
sin ese caso no se genera ninguna sugerencia.

`discard()` y `postpone()` devuelven nuevas instancias; no mutan historial ni
persisten estados. Por defecto, `POSTPONED` no consume el límite de ocurrencias:
la sugerencia vuelve a estar disponible después del cooldown configurado (y de
inmediato si el cooldown es cero). `DISCARDED`, en cambio, no activa cooldown,
pero sí consume el límite. `postponed_counts_toward_limit=True` permite una
política explícita distinta.

La identidad y todos los índices de resumen, caso y contexto usan
`(enrollment_id, edition_id)`. Un duplicado conflictivo para esa clave se
rechaza; nunca se sobrescribe silenciosamente. Los contextos de renderizado
también deben usar esa clave.

El estado `RecommendationStatus.POSTPONED` es local a este módulo y no añade un
estado a `domain.CommunicationStatus` ni persiste nada (#21 queda fuera de este
Issue). En una futura adaptación a #21 debe mapearse a un estado local de
revisión pospuesta, conservando el evento histórico y sus fechas; no se debe
tratar automáticamente como `DISCARDED`. Las entradas históricas con
`status=None` son deliberadamente neutrales cuando la fuente todavía no ofrece
un estado de persistencia, evitando inventar `HISTORICAL` como estado de dominio.
El renderizado es opcional y delega sin cambios en `message_templates.render_message`.
