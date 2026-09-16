# Validation Report

## Issue

`#101 - Registrar auditoría y retención de generaciones IA`

## Implementation Summary

Se implementó la auditoría local de generaciones con metadatos mínimos,
modelo, versión de prompt, timestamps, estados, hash SHA-256, referencia UUID
al texto y códigos de error no sensibles. El texto de los borradores se
mantiene separado en `data/local/generation-text/`, una ruta ignorada por Git,
y puede recuperarse, borrarse y someterse a retención explícita. Se añadieron
transiciones de estado, registro mínimo de fallos, migración aditiva de bases
existentes, índices, configuración de retención de 30 días y documentación de
privacidad, recuperación, borrado y límites operativos. No se añadió envío
automático ni ninguna integración remota.

## Files Changed

- `.gitignore`
- `docs/local-generation-contract.md`
- `docs/privacy-security-retention.md`
- `src/adams_tutoria/config.py`
- `src/adams_tutoria/dashboard.py`
- `src/adams_tutoria/generation.py`
- `src/adams_tutoria/persistence/database.py`
- `src/adams_tutoria/persistence/repositories.py`
- `src/adams_tutoria/persistence/schema.py`
- `tests/unit/test_generation.py`
- `tests/unit/test_persistence.py`
- `docs/validation/issue-101-validation-report.md`

## Acceptance Criteria

- **PASS** — Se guardan todos los metadatos mínimos indicados — la auditoría
  persiste matrícula, tipo, modelo, versión de prompt, timestamps, estado,
  hash/referencia mínima y código de error sin conservar texto completo en
  SQLite; las pruebas cubren preservación y recuperación de metadatos.
- **PASS** — Texto solo en almacenamiento local ignorado según política — los
  borradores se escriben en `data/local/generation-text/`, se referencian por
  UUID y `.gitignore` cubre la ruta; la prueba verifica separación y
  recuperación.
- **PASS** — No hay prompts/textos reales en Git ni logs — el payload usa la
  allowlist existente, el historial y los fallos solo guardan metadatos y
  códigos de excepción, y la revisión de privacidad no detectó exposición de
  texto, prompts, PII, credenciales ni datos reales.
- **PASS** — Se registran `REVIEWED`, `EDITED`, `COPIED`, `DISCARDED` y `SENT`
  manual — las transiciones e historial se persisten sin efectos de envío; las
  pruebas cubren el flujo de estados y la restricción de `SENT` manual.
- **PASS** — Retención y borrado documentados y aplicados — `delete` y
  `retain(before)` eliminan registro y archivo de forma idempotente, con
  recuperación ante fallo de persistencia; la política de referencia de 30 días
  y la invocación manual están documentadas.
- **PASS** — Pruebas de privacidad y recuperación/borrado sintéticas — las
  pruebas usan únicamente datos sintéticos y verifican migración, rutas,
  recuperación, borrado, retención, fallos aislados y ausencia de envío.

## Validation Executed

### `uv run pytest`

- Result: `PASS`
- Notes: 316 pruebas pasaron.

### `uv run ruff check .`

- Result: `PASS`
- Notes: Sin errores de lint.

### `uv run ruff format --check .`

- Result: `PASS`
- Notes: Todos los archivos están formateados.

### `uv run mypy src`

- Result: `PASS`
- Notes: Sin errores de tipado en `src`.

### Validación de migración y compatibilidad

- Result: `PASS`
- Notes: La migración aditiva de `generation_record`, las tablas de historial y
  fallos y los índices se verificaron con una base legacy sintética y con la
  inicialización idempotente.

### Validación de rutas y almacenamiento separado

- Result: `PASS`
- Notes: La ruta configurable de texto queda bajo el directorio local
  ignorado; la recuperación valida la referencia y no permite salir de la
  carpeta de artefactos.

### Validación de fallos y aislamiento

- Result: `PASS`
- Notes: Los fallos por matrícula se aíslan, no persisten un borrador fallido y
  registran únicamente instante UTC y nombre de excepción como `error_code`,
  sin texto del error ni PII.

### Validación de privacidad y protección de datos

- Result: `PASS`
- Notes: Revisión del diff, documentación y pruebas: no hay credenciales,
  secretos, datos reales, exports, bases operativas, prompts completos ni
  textos reales versionados o expuestos en logs.

### Validación de no-envío

- Result: `PASS`
- Notes: No se añadieron llamadas remotas, transporte ADAMS, SMTP ni envío
  automático; `SENT` continúa siendo únicamente una marca manual posterior a
  `COPIED`.

### `git diff --check`

- Result: `PASS`
- Notes: Sin errores de espacios o líneas defectuosas.

## Risks and Limitations

- Persisten datetimes naive en superficies legacy o datos previos; el código
  nuevo normaliza timestamps recuperados a UTC, pero no elimina esa deuda de
  compatibilidad.
- Se mantienen legacy offsets en datos o formatos históricos; la migración es
  aditiva y compatible, no una reescritura de esos valores.
- `text_dir` puede configurarse a una ruta custom; la política de seguridad
  depende de que el operador mantenga esa ruta en almacenamiento local ignorado.
- `retain(before)` procesa borrados por registro y no es atómico como lote: un
  fallo intermedio puede dejar parte del lote eliminada y parte pendiente.
- `_safe_error` permanece como código muerto no utilizado y puede requerir
  limpieza posterior.
- El plan de prompt no está versionado como entidad independiente; se conserva
  la versión recibida en los metadatos, sin resolver la gobernanza futura de
  planes/versiones.
- No existe tarea automática de retención; el operador debe invocar
  explícitamente `retain(before)`.

## Out-of-Scope Changes

`None`

## Final Status

`READY FOR HUMAN REVIEW`
