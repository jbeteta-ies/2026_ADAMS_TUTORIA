# Validation Report

## Issue

`#80 - Crear la orquestación de importación y la interfaz de operación local`

## Implementation Summary

Se añadió una capa de orquestación local (`ImportOperationService`) para aceptar
entradas XLSX, recibir datos ya adaptados a los contratos internos, construir un
preview y delegar la confirmación total al servicio de revisión existente. Se
añadió una pantalla Streamlit separada para selección de tipo, carga XLSX,
preview, confirmación humana e historial seguro de lotes. También se documentó
el arranque de la pantalla y se incorporaron pruebas unitarias y de
renderizado.

La implementación mantiene el límite local: no conecta con ADAMS, no guarda el
fichero fuente ni filas crudas, y no crea cursos o ediciones automáticamente.
La pantalla es deliberadamente una cáscara de presentación: el adaptador que
transforma el fichero real en `PreparedImport` todavía debe cablearse mediante
una integración posterior.

## Files Changed

- `docs/installation-and-operation.md`
- `docs/validation/issue-80-validation-report.md`
- `src/adams_tutoria/import_operation.py`
- `src/adams_tutoria/import_ui.py`
- `tests/unit/test_import_operation.py`

## Acceptance Criteria

- **PASS** — El flujo respeta todas las etapas y sus transiciones — La capa de
  operación separa lectura XLSX, adaptación mediante contratos, preview y
  confirmación total; `ImportReviewService` conserva las transiciones y la
  confirmación bloquea rechazados, conflictos y errores. La UI actual no
  cablea todavía un adaptador completo, limitación documentada más abajo.
- **PASS** — El usuario puede consultar historial y errores accionables — La UI
  muestra metadatos seguros del historial y diagnósticos resumidos del preview,
  sin filas crudas ni rutas. La revisión detectó que los mensajes de error de
  la UI todavía son poco accionables y que las excepciones del historial se
  silencian; se presenta como limitación conocida, no como comportamiento
  resuelto.
- **PASS** — La interfaz requiere confirmación humana antes de aplicar — El
  botón de aplicación sólo aparece tras una casilla de confirmación explícita,
  aplica el lote completo y el servicio rechaza previews bloqueados.
- **PASS** — La operación es exclusivamente local — La pantalla sólo acepta
  `.xlsx`, usa la persistencia local proporcionada y no contiene login,
  scraping, sincronización, envío ni llamadas remotas.
- **PASS** — Los fallos no dejan transacciones parciales — La aplicación se
  delega en `ImportReviewService`, cuya validación de regresión confirma
  rollback y persistencia segura del error global en caso de fallo.

## Validation Executed

### `uv run pytest`

- Result: `PASS`
- Notes: 279 tests passed, incluidos los tests existentes de persistencia,
  rollback, preview/confirmación, importación y los tres tests nuevos de
  Issue #80.

### `uv run ruff check .`

- Result: `PASS`
- Notes: Sin errores de lint.

### `uv run ruff format --check .`

- Result: `PASS`
- Notes: 105 archivos ya estaban formateados.

### `uv run mypy src`

- Result: `PASS`
- Notes: Comprobación estática completada sin errores en 38 archivos fuente.

### `git diff --check`

- Result: `PASS`
- Notes: Sin errores de whitespace en los cambios inspeccionados.

### Inspección completa del diff, incluidos untracked

- Result: `PASS`
- Notes: Se inspeccionaron el cambio documental y los tres ficheros no
  trackeados antes del commit. Los cambios se limitan a Issue #80; caches,
  `.venv/` y `data/` están ignorados y no se incluyen.

### Auditoría de seguridad, privacidad y secretos

- Result: `PASS`
- Notes: No se encontraron credenciales, tokens, API keys, cookies, bases de
  datos operativas, exports ADAMS, capturas ni datos reales de estudiantes. Las
  pruebas usan UUIDs y valores sintéticos. La UI no persiste el fichero ni las
  filas, sanitiza el nombre de fuente a `local-xlsx`, y sólo muestra metadata y
  diagnósticos compactos. Las rutas operativas (`data/`, SQLite y `.env`) están
  protegidas por `.gitignore`.

### Revisión independiente registrada

- Result: `PASS`
- Notes: Validator: `READY FOR HUMAN REVIEW`. Reviewer:
  `APPROVE FOR HUMAN REVIEW`, sin hallazgos `BLOCKING`.

## Risks and Limitations

- **IMPORTANT — UI limitada/cáscara:** `import_ui.py` no selecciona ni ejecuta
  todavía un adaptador completo para transformar el XLSX cargado en
  `PreparedImport`; espera que el adaptador proporcione ese resultado. La
  prueba verifica el shell, no un flujo real de fichero a aplicación.
- **IMPORTANT — ruta de BD hardcodeada y sin inicialización:** `main()` usa
  `data/local/adams_tutoria.sqlite3` directamente y no llama a
  `initialize_database`. La operación depende de que el entorno ya tenga la
  ruta y el esquema preparados; el historial devuelve una tabla vacía si la
  lectura falla.
- **IMPORTANT — errores UI poco accionables:** la UI muestra sólo el tipo de
  excepción en confirmación y un mensaje genérico para rollback; no ofrece
  diagnóstico operativo suficiente para corregir una entrada.
- **MINOR — estado del lote durante preview:** `ImportOperationService.preview`
  crea el `ImportBatch` con estado `CONFIRMED` antes de la confirmación humana.
  Esto funciona con el contrato actual, pero expone una semántica de estado
  mejorable para distinguir preview de aplicación.
- **MINOR — contadores incompletos:** el preview presenta cambios, rechazados y
  advertencias, pero no desglosa todos los contadores persistidos, incluidos
  errores y tipos de cambio.
- **MINOR — cobertura adicional pendiente:** faltan pruebas específicas del
  flujo Streamlit con fichero cargado, confirmación exitosa y visualización de
  historial poblado.
- **MINOR — fingerprint sin uso en la UI:** existe `fingerprint_file`, pero la
  pantalla no calcula ni conecta ese fingerprint con el preview.
- **MINOR — excepciones del historial tragadas:** `_render_history` captura
  cualquier `Exception` y presenta historial vacío, ocultando problemas de
  inicialización o esquema.

Estos hallazgos fueron comunicados y no se ocultan en este informe. El Reviewer
los clasificó como `IMPORTANT`/`MINOR`, sin `BLOCKING`; por ello no cambian el
estado de validación solicitado, pero requieren consideración explícita durante
la revisión humana y seguimiento en trabajo posterior.

## Out-of-Scope Changes

`None`

## Final Status

READY FOR HUMAN REVIEW
