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

## Copia y envío manual

El dashboard muestra el mensaje completo únicamente después de que el tutor
aprueba explícitamente la sugerencia. El tutor puede seleccionarlo o descargar
un fichero de texto para copiarlo manualmente en ADAMS; esas acciones no hacen
ninguna llamada externa. Después de copiarlo, debe pulsar la acción explícita
que registra `COPIED`. Tras realizar el envío manual en ADAMS, debe pulsar la
acción separada que registra `SENT`. El texto renderizado no se persiste: el
historial conserva solo estados y marcas temporales.

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
