# Auditoría de privacidad, seguridad y retención

Este documento registra la revisión de la Issue #31 sobre el manejo local de
datos personales. La revisión se hizo sobre código, configuración,
documentación y rutas versionadas; no se abrieron ni copiaron bases de datos,
exports, backups o cualquier otro dato operativo local.

## Alcance y clasificación

La aplicación puede manejar nombres, emails, identificadores externos,
progreso, evaluaciones, acciones del tutor y el historial estructurado de
comunicaciones. Son datos personales o potencialmente vinculables a una
persona. Los ejemplos y tests del repositorio usan únicamente datos sintéticos.

El repositorio contiene código y documentación segura, no el almacén
operativo. El uso actual es local y el envío de mensajes a ADAMS sigue siendo
manual; no hay autenticación, integración de envío ni cifrado en este alcance.

## Rutas y configuración

La pantalla Settings solo persiste en SQLite local los valores técnicos
allowlisted de Ollama (modelo, endpoint loopback, temperatura, límite y
timeout). Rechaza claves desconocidas y destinos remotos. La ausencia del
modelo persistido se muestra como error y no activa fallback.

| Superficie | Resultado de la auditoría | Mitigación vigente |
| --- | --- | --- |
| `data/private/` | Adecuada para exports, importaciones y comunicaciones privadas | `data/` está ignorado por Git |
| `data/local/` | Adecuada para estado local y SQLite | `data/` está ignorado por Git |
| `ADAMS_TUTORIA_*` | Las rutas son configurables y se representan sin leer ni crear archivos durante la carga | Revisar la ruta efectiva antes de operar; mantenerla fuera de rutas versionadas |
| rutas relativas | Se resuelven respecto a `base_dir` | Usar un directorio de datos local dedicado; no configurar el repositorio como destino operativo |

La configuración no crea directorios, abre SQLite ni lee variables al importar
el módulo. Una ruta configurada fuera de `data/` puede no quedar protegida por
`.gitignore`; esto es un riesgo operacional conocido y requiere revisión local
antes de usarla. No se introduce en esta Issue una validación de rutas ni una
nueva arquitectura.

## SQLite

La base operativa se ubica en `AppConfig.local_data_dir` con nombre
`adams_tutoria.sqlite3`. La conexión habilita claves foráneas, confirma la
transacción únicamente al salir correctamente y hace rollback ante errores.
La inicialización es explícita, no ocurre al importar el paquete, y el diseño
actual no usa WAL, ORM ni migraciones.

La base contiene campos identificables (`student.full_name`, `student.email`)
y datos de progreso, evaluación, acciones y comunicaciones. Por tanto, debe
permanecer en una ruta local ignorada. Los tests de persistencia usan `tmp_path`
y no la base operativa.

**Riesgo residual:** no hay cifrado en reposo ni control de acceso de la base.
La protección depende de los permisos del sistema operativo y del entorno local.
No se implementan cifrado, autenticación ni migraciones en esta Issue.

## Imports y exports

Los lectores tabulares aceptan archivos locales CSV/XLSX y producen mappings
estructurales; no persisten filas ni copian la fuente. Los diagnósticos usan
nombre de fuente, tipo y ordinal de fila, y no incluyen la fila completa.
Los contratos de importación advierten que los valores deben limitarse a lo
necesario y no incluir credenciales ni datos no requeridos.

No existe una ruta de exportación operativa en el código auditado. Cualquier
export o fuente real debe permanecer bajo `data/private/` o `data/local/` y no
debe copiarse a `tests/`, `docs/` ni otra ruta versionada.

## Comunicaciones

Los registros de comunicación guardan códigos estructurados, timestamps,
claves de deduplicación y referencias a la matrícula; no guardan texto libre
de mensajes en la entidad persistida. Las plantillas se renderizan localmente
para revisión humana y el copiado/envío a ADAMS es manual.

Los mensajes personalizados o copiados que contengan datos reales deben
permanecer en almacenamiento local ignorado. Los tests y ejemplos solo usan
destinatarios sintéticos. No se autoriza el envío automático como resultado de
esta auditoría.

Los borradores de generación local (`draft_text`) pueden contener texto de
comunicación y, por tanto, deben tratarse como datos potencialmente personales:
se guardan únicamente en la SQLite local ignorada bajo `data/`, no se incluyen
en payloads del modelo ni en documentación, logs o fixtures versionados. El
operador debe borrar explícitamente los borradores y sus copias locales cuando
ya no sean necesarios; también debe eliminar backups o sidecars que los
contengan. No hay borrado ni retención automática implementados: hasta que una
Issue futura defina plazos y automatización, se aplica minimización y revisión
manual periódica.

## Logs y errores

El dashboard consulta repositorios existentes y no crea cursos, ediciones,
matrículas, perfiles ni datos sintéticos al renderizar. El payload de Ollama
se construye únicamente desde el contexto minimizado permitido por el contrato
de generación; no contiene filas crudas, credenciales, sesiones, contacto ni
informes completos. La respuesta registra solo el modelo reportado por Ollama,
no el prompt ni la respuesta completa.

No hay un subsistema de logging persistente configurado en la aplicación. La
salida de arranque es un banner sin datos personales. Los errores de
validación revisados son mensajes de estructura/código y no imprimen filas
completas; los adaptadores mantienen diagnósticos acotados.

Si se añade logging en el futuro, debe registrar conteos, códigos y
identificadores internos mínimos, nunca nombres, emails, filas completas,
tokens o mensajes personalizados. Los logs operativos deben vivir bajo
`data/`, que está ignorado.

## Backups

No hay mecanismo de backup implementado ni backups versionados en el
repositorio. Backups manuales de SQLite, exports o comunicaciones contienen
datos potencialmente personales y deben guardarse fuera del repositorio,
preferentemente bajo `data/private/` o `data/local/`.

`.gitignore` cubre `data/`, bases SQLite y extensiones habituales de backup
(`.bak`, `.backup`, `.dump`), incluidos sus sidecars SQLite. Esta protección
no sustituye comprobar la ubicación y los permisos del backup antes de
crearlo.

## Fixtures y documentación

No se inspeccionan ni incorporan datos operativos. Los tests existentes usan
identidades inventadas, UUIDs deterministas o valores neutros. Los fixtures
versionados, si se añaden, deben ser sintéticos y estar marcados como tales;
no deben ser exports reales ligeramente modificados.

La documentación puede describir contratos y rutas, pero no debe contener
nombres reales, emails reales, identificadores ADAMS, capturas sin redactar ni
contenido de comunicaciones reales.

## Retención y eliminación

Los fallos de generación registran únicamente `error_code` e instante UTC en
`generation_failure`; nunca se conserva el texto de la excepción ni PII.

La auditoría de generaciones usa archivos UUID en `data/local/generation-text/`
(ruta ignorada), con hash y referencia en SQLite, nunca prompts o textos completos.
La política operativa de referencia es de 30 días desde `created_at`; no existe
una tarea automática. El operador invoca explícitamente `retain(before)`, que
borra registro y archivo de manera coordinada e idempotente.

No existe todavía una política automática de retención ni una tarea de
eliminación. El operador local es responsable de conservar solo el tiempo
necesario los exports, bases, comunicaciones y backups, y de eliminar también
copias y sidecars asociados cuando dejan de ser necesarios.

Hasta que una Issue futura defina plazos y un mecanismo aprobado, la
mitigación es: minimizar las copias, no versionar datos, no duplicar exports
en el modelo, revisar periódicamente `data/` y borrar manualmente los datos
operativos que ya no sean necesarios.

## Hallazgos y estado

- **Mitigado:** rutas operativas documentadas e ignoradas; SQLite y sidecars
  cubiertos; secretos `.env` ignorados.
- **Mitigado:** fixtures y ejemplos se mantienen sintéticos; los tests de
  seguridad verifican rutas representativas y esta auditoría.
- **Riesgo residual aceptado en alcance:** sin cifrado, autenticación, backup
  automático ni retención automática.
- **Riesgo operativo:** una ruta configurada fuera de `data/` puede quedar
  fuera de las reglas de `.gitignore`; debe verificarse antes de usarla.

Esta auditoría no introduce cifrado, autenticación, migraciones,
dependencias nuevas ni cambios de arquitectura.

La validación integral de la Issue #82 repite esta auditoría sobre rutas
versionadas, secretos y bases operativas sin abrir la base local existente. Las
pruebas crean SQLite exclusivamente bajo `tmp_path` y usan identidades
sintéticas. También cubren que una confirmación parcialmente fallida no deje
entidades aplicadas fuera de la transacción y que los adaptadores no Excel
recorran el mismo flujo de revisión.
