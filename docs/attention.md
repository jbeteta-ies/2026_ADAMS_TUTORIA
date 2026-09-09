# Cola de atención

`adams_tutoria.attention.prioritize_attention` construye una cola operativa
para el tutor a partir de `EnrollmentSummary`. Ese es el único contrato de
entrada: no acepta ni consulta `ProgressSnapshot`, `Evaluation` ni
`FollowUpAssessment` por separado, y no invoca las reglas de seguimiento.

## Contrato y explicación

El resultado es una tupla inmutable de `AttentionCase`. Cada caso contiene
`enrollment_id`, `edition_id`, una puntuación `Decimal`, un `PriorityLevel`
operativo (`LOW`, `MEDIUM`, `HIGH` o `CRITICAL`) y los mismos objetos
`FollowUpReason` del resumen. Por ello se conservan tanto sus códigos como sus
explicaciones originales. Los resúmenes cuyo `needs_follow_up` es falso no
aparecen.

La puntuación es la suma de los pesos configurados de las razones que
requieren seguimiento. Los códigos desconocidos producen un error explícito;
no existe un peso implícito. Los pesos son no negativos y los umbrales se
configuran mediante `PriorityThresholds`.

## Duplicados, filtro y determinismo

La deduplicación usa únicamente `enrollment_id`. Resúmenes equivalentes se
colapsan. Si dos resúmenes con ese identificador difieren, se lanza
`ConflictingSummaryError` de forma determinista, en lugar de escoger uno
silenciosamente. El parámetro opcional `edition_id` filtra antes de esa
deduplicación.

La salida se ordena por prioridad operativa descendente, puntuación
descendente y los UUID de edición y matrícula. Las razones se ordenan
establemente por código y explicación, sin reconstruirlas. No se usan nombres
ni correos electrónicos.

## Limitaciones y futuro

Este módulo no persiste datos, no envía comunicaciones, no presenta UI y no
consulta ADAMS. Tampoco define nuevas reglas de seguimiento ni decide si una
razón debe existir. La exclusión futura de casos (por ejemplo, atención ya
resuelta) deberá incorporarse mediante una decisión de producto y un contrato
explícito; no se infiere aquí.
