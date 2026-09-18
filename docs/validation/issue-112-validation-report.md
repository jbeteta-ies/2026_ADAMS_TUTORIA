# Validation Report

## Issue

`#112 - Implementar importación de evolución/progreso desde XLSX`

## Implementation Summary

Se validó la importación local, revisable, transaccional e idempotente del estado
actual de evolución desde XLSX. El flujo procesa bloques de alumno, genera
preview y diagnósticos privacy-safe antes de aplicar cambios, limita el contenido
a módulos 1--4 y sus submódulos permitidos, conserva la columna G separada del
progreso de páginas y usa estado actual por matrícula y contenido. Requiere
confirmación humana y la resolución de matrículas existentes de #110. No genera
ni envía comunicaciones.

## Files Changed

- `src/adams_tutoria/evolution_xlsx.py`
- `src/adams_tutoria/tabular_import.py`
- `src/adams_tutoria/persistence/database.py`
- `src/adams_tutoria/persistence/schema.py`
- `tests/unit/test_evolution_xlsx.py`
- `tests/unit/test_persistence.py`
- `docs/adams-progress-adapter.md`
- `docs/installation-and-operation.md`
- `docs/issue-112-specification-evidence.md`
- `docs/validation/issue-112-validation-report.md`

## Acceptance Criteria

1. **PASS** — La Issue conserva la dependencia de #110 y la importación solo se aplica a matrículas existentes — se resuelve mediante identidad estable y no se crean entidades para bloques no resolubles.
2. **PASS** — El XLSX se procesa por bloques de alumno, con preview y diagnósticos antes de aplicar cambios — la preparación está separada de la aplicación confirmada y devuelve resumen y diagnósticos.
3. **PASS** — Solo se importan módulos 1-4 y submódulos numerados por módulo+número romano — el adaptador limita el alcance a esos patrones.
4. **PASS** — `Presentación`, `Resumen`, `Caso práctico final`, actividades y evaluaciones quedan excluidos — producen exclusión o diagnóstico sin importación.
5. **PASS** — La primera importación crea la estructura permitida sin inventar nodos o jerarquías — solo se crean nodos respaldados por contenido permitido y estructura disponible.
6. **PASS** — Las importaciones siguientes hacen upsert del estado actual y no crean duplicados — la persistencia usa identidad única por matrícula/contenido.
7. **PASS** — No se conserva histórico de snapshots de progreso en esta implementación — el flujo escribe estado actual separado del modelo histórico de snapshots.
8. **PASS** — La ausencia posterior de un módulo/submódulo conserva su último estado conocido — no se convierte en cero ni se elimina.
9. **PASS** — La fecha de importación queda registrada como última actualización del estado actual — se conserva en los registros del lote.
10. **PASS** — El porcentaje de páginas visualizadas acepta únicamente valores entre 0 y 100, inclusive — los límites se aceptan y los valores inválidos se diagnostican.
11. **PASS** — El porcentaje global de la columna G se conserva separado del porcentaje de páginas visualizadas — se almacenan y procesan en campos distintos.
12. **PASS** — Los valores inválidos, ambiguos o no resolubles generan diagnóstico y no se transforman silenciosamente — el adaptador diagnostica sin conversiones silenciosas.
13. **PASS** — La identidad del alumno/matrícula se resuelve mediante un identificador estable aprobado, sin heurísticas implícitas — no se usa nombre ni posición para matching.
14. **PASS** — La aplicación requiere confirmación humana y es transaccional e idempotente — preview no escribe; apply confirmado es idempotente y rollback revierte estado, estructura y auditoría.
15. **PASS** — La estructura resultante permite identificar módulos/submódulos relevantes para futuros correos, sin implementar esos correos — no se añadió generación ni envío de comunicaciones.
16. **PASS** — Las pruebas y fixtures contienen exclusivamente datos sintéticos/anónimos y verifican las reglas de privacidad — no conservan identificadores, nombres, correos ni filas completas.

### Decisiones M1--M5

- **PASS — M1 Custodia/evidencia** — la evidencia autorizada permanece fuera del repositorio y no se usa como fixture, log ni documentación reproducible.
- **PASS — M2 Lector genérico/adaptador** — el lector estructural permanece separado del adaptador específico de evolución XLSX.
- **PASS — M3 API operativa preview/apply** — `confirm=False` prepara preview sin escritura y `confirm=True` aplica tras confirmación humana.
- **PASS — M4 Contadores/auditoría no solapados** — cambios y no cambios se mantienen separados de rechazos y exclusiones; la auditoría no conserva filas fuente ni PII.
- **PASS — M5 Mensajes privacy-safe** — los diagnósticos exponen códigos, fila y mensajes genéricos, sin identificadores ni datos personales.

## Validation Executed

### `uv run pytest -q`

- Result: `PASS`
- Notes: `336 passed`.

### `uv run ruff check .`

- Result: `PASS`
- Notes: Sin errores de lint.

### `uv run ruff format --check .`

- Result: `PASS`
- Notes: El formato de Ruff está conforme.

### `uv run mypy src`

- Result: `PASS`
- Notes: Sin errores de tipado en `src`.

### `uv run adams-tutoria`

- Result: `PASS`
- Notes: El ejecutable local arrancó correctamente.

### `uv run python -m adams_tutoria`

- Result: `PASS`
- Notes: El módulo ejecutable arrancó correctamente.

### Probe de preview sin confirmación

- Result: `PASS`
- Notes: `confirm=False` produjo preview y diagnósticos sin escribir cambios persistentes.

### Probe de apply confirmado

- Result: `PASS`
- Notes: `confirm=True` aplicó el lote sintético tras la confirmación y registró los cambios esperados.

### Probe de idempotencia

- Result: `PASS`
- Notes: La repetición del mismo lote no creó duplicados y clasificó como no cambiados los valores ya persistidos.

### Probe de rollback transaccional

- Result: `PASS`
- Notes: Un fallo sintético durante `apply` revirtió estado, estructura y auditoría del lote.

### Probe de privacidad

- Result: `PASS`
- Notes: Los fixtures fueron sintéticos/anónimos y los diagnósticos/auditoría no conservaron identificadores, nombres, correos ni filas fuente.

## Risks and Limitations

- La validación usa workbooks sintéticos; no demuestra variantes de un XLSX operativo distintas del contrato confirmado.
- La resolución depende de que la edición, el alumno y la matrícula de #110 ya existan; un bloque no resoluble se rechaza y no crea entidades.
- El parser es deliberadamente estricto: cabeceras, vacíos, duplicados, escalas o categorías no confirmadas se diagnostican o excluyen, no se infieren.
- La API opera con argumentos `str | Path | BinaryIO`; no se validó una interfaz UI o CLI adicional específica para el importador.
- No se implementan cifrado, WAL ni migraciones versionadas para estas tablas de estado actual.
- No se generan ni envían comunicaciones; la identificación de contenido solo deja preparada la consulta futura.

## Out-of-Scope Changes

`None`

## Final Status

`READY FOR HUMAN REVIEW`
