# Validation Report

## Issue

`#81 - Generalizar el contrato para futuros conectores`

## Implementation Summary

La implementación separa el punto de entrada de adaptadores del pipeline común
de importación. Añade un `ImportDataset` normalizado, el protocolo
`ImportDatasetAdapter` y un adaptador sintético en memoria, y permite que
`ImportOperationService` lleve fuentes no Excel hasta la previsualización y la
confirmación explícita existente. La persistencia conserva únicamente
metadatos seguros de procedencia; la UI y la documentación describen la
frontera genérica y mantienen Excel en el borde de adaptación.

La solución no implementa conectores remotos, scraping ni OCR, y todos los
ejemplos y tests añadidos son sintéticos.

## Files Changed

- `README.md`
- `docs/import-contract.md`
- `docs/validation/issue-81-validation-report.md`
- `src/adams_tutoria/import_operation.py`
- `src/adams_tutoria/import_pipeline.py`
- `src/adams_tutoria/import_ui.py`
- `tests/integration/test_source_independent_import.py`
- `tests/unit/test_import_operation.py`

## Acceptance Criteria

- **PASS** — Cada responsabilidad tiene una frontera explícita y testeable — `ImportDatasetAdapter`/`ImportDataset` separan adaptación y normalización; `ImportOperationService` delega preview/confirmación; `ImportReviewService` conserva la revisión y aplicación atómica. La integración sintética verifica el recorrido común y la suite completa pasa.
- **PASS** — Excel es un adaptador, no una dependencia del dominio — La lectura XLSX permanece en `read_xlsx`/`tabular_import`; la operación genérica recibe el protocolo de adaptador y traduce el formato `xlsx` a `ImportSourceType.EXCEL` únicamente en el límite de aplicación. La persistencia y la UI no reciben filas ni ficheros Excel como contrato interno.
- **PASS** — Puede añadirse una fuente no Excel sin reescribir persistencia ni UI — `InMemoryImportAdapter` implementa el protocolo sin modificar persistencia ni UI y alcanza el mismo preview; el test `test_synthetic_non_excel_adapter_reaches_common_preview` lo verifica. Las fuentes desconocidas se almacenan como `ImportSourceType.OTHER` y con nombre seguro `local-source`.
- **PASS** — El ejemplo es sintético y no contiene datos reales — El adaptador en memoria y sus tests usan datasets vacíos/sintéticos, SQLite bajo `tmp_path` y ninguna credencial, exportación o dato personal real.
- **PASS** — Se documentan puntos de extensión y errores — `docs/import-contract.md` documenta fronteras, incorporación de adaptadores, diagnósticos seguros, rechazo de datasets inválidos, confirmación bloqueada y restricciones de no crear cursos/ediciones, no persistir input bruto y no enviar datos remotamente.

## Validation Executed

### `uv run pytest`

- Result: `PASS`
- Notes: 282 tests passed in 2.44s, incluidos los tests unitarios de mapeo de
  tipos de fuente y el test de integración del adaptador no Excel.

### `uv run ruff check .`

- Result: `PASS`
- Notes: No lint errors; 39 archivos fuente analizados.

### `uv run ruff format --check .`

- Result: `PASS`
- Notes: 108 archivos ya estaban formateados.

### `uv run mypy src`

- Result: `PASS`
- Notes: No se encontraron problemas de tipado en 39 archivos fuente.

### `git diff --check`

- Result: `PASS`
- Notes: No se detectaron errores de whitespace en el diff.

### Inspección completa del diff y del estado Git

- Result: `PASS`
- Notes: Se inspeccionaron todos los cambios tracked y los dos archivos nuevos
  de código/tests, además del contexto de Issue #81. El diff se limita a la
  generalización del contrato, su documentación, tests y este informe.

### Revisión de seguridad y protección de datos

- Result: `PASS`
- Notes: Se aplicó la revisión de `student-data-safety`. No hay credenciales,
  tokens, cookies, bases de datos operativas ni datos reales de estudiantes.
  Los tests usan datos sintéticos y bases bajo `tmp_path`; el código reduce el
  nombre de fuente a etiquetas seguras (`local-xlsx`, `local-csv` o
  `local-source`) y no conserva ficheros ni filas brutas.

### Revisión independiente

- Result: `PASS`
- Notes: Reviewer outcome: `APPROVE FOR HUMAN REVIEW`, sin bloqueos. Se
  incorporan como hallazgos menores/limitaciones para revisión humana: existe
  acoplamiento nominal residual a `excel_contract` porque los tipos
  `ProgressRecord` y `EvaluationRecord` todavía se importan desde ese módulo;
  `source_name` de entrada se descarta deliberadamente y se persiste una
  etiqueta segura; las fuentes genéricas se clasifican como
  `source_kind=other`; y quedan mejoras menores posibles de tipado y
  documentación. Ninguno fue considerado bloqueante por el Reviewer.

## Risks and Limitations

- El acoplamiento nominal a `excel_contract` de `ProgressRecord` y
  `EvaluationRecord` permanece como deuda técnica menor; el contrato de
  importación es funcionalmente genérico, pero una futura extracción de esos
  tipos podría eliminar la referencia nominal.
- `source_name` no se conserva literalmente: se descarta para evitar persistir
  rutas o nombres proporcionados por el usuario y se reemplaza por una etiqueta
  segura. Esto limita la trazabilidad nominal, aunque evita filtrar datos
  sensibles.
- `ImportOperationService.prepare` clasifica fuentes adaptadas por ese camino
  como `source_kind=other`; los adaptadores concretos pueden usar el mapeo
  explícito de `preview` cuando necesiten distinguir `xlsx` o `csv`.
- Persisten mejoras menores de tipado (por ejemplo, las tuplas de diagnósticos
  del adaptador sintético no están parametrizadas con tipos concretos) y de
  documentación, identificadas por el Reviewer como no bloqueantes.
- La solución establece fronteras y un ejemplo no Excel, pero no implementa
  conectores remotos, scraping, OCR ni parsing de nuevas fuentes concretas,
  conforme al alcance de la Issue.

## Out-of-Scope Changes

`None`

## Final Status

`READY FOR HUMAN REVIEW`
