# Historial de comunicaciones

`CommunicationRecordRepository` es el único almacén del historial. Registra
identificadores y fechas de acciones del tutor, pero no guarda texto de
mensajes ni datos personales adicionales. Los estados válidos son
`SUGGESTED -> APPROVED|DISCARDED|POSTPONED`, `POSTPONED -> APPROVED|DISCARDED`,
`APPROVED -> COPIED|SENT` y `COPIED -> SENT`; los estados finales no se pueden
reabrir. `APPROVED -> SENT` se permite directamente y deja `copied_at` en
`None`; nunca se inventa una fecha de copia. Las fechas deben respetar
`reviewed_at >= suggested_at`, `copied_at >= reviewed_at` y
`sent_at >= copied_at` cuando existe, y todas deben incluir zona horaria.
`postponed_at` se conserva al aprobar o descartar una comunicación pospuesta.

La inicialización evoluciona bases existentes únicamente de forma aditiva:
añade las cinco columnas nuevas e índices si faltan, conservando las diez
columnas y filas anteriores. No hay migración destructiva ni segunda base de
datos. Los registros antiguos se leen con el identificador de edición de su
matrícula cuando no tienen `edition_id`.

`CommunicationHistoryAdapter` ofrece una proyección de solo lectura del
contrato de historial de las recomendaciones de #20, con filtros opcionales de
matrícula y edición. La lógica de repetición permanece en #20 y no se envían
mensajes ni se usan credenciales externas. El estado persistido `POSTPONED` se
traduce al `RecommendationStatus.POSTPONED` esperado por #20.
