# Issue #112: especificación y evidencia del formato de evolución

## Propósito y límite de este documento

Este documento implementa únicamente la fase de especificación/evidencia del
plan aprobado para el Issue #112. No implementa un importador funcional, no
crea tablas ni migraciones y no convierte el XLSX operativo en datos del
repositorio.

La regla de esta auditoría es separar lo que está confirmado por el
repositorio de las decisiones aprobadas para el diseño y de lo que sigue sin
evidencia. Una decisión aprobada no constituye evidencia de que el formato
real de ADAMS la cumpla.

## Fuentes autorizadas consultadas

- Issue #112, incluido su plan revisado/aprobado y criterios de parada.
- Issue #110 y su contrato aprobado. El Issue está cerrado.
- `src/adams_tutoria/tabular_import.py`, `src/adams_tutoria/excel_contract.py` y
  `docs/tabular-import.md` para el lector estructural genérico.
- `src/adams_tutoria/adapters/adams/progress.py` y
  `docs/adams-progress-adapter.md` para el adaptador provisional.
- `src/adams_tutoria/domain.py`, `src/adams_tutoria/persistence/schema.py` y
  `src/adams_tutoria/persistence/database.py` para el modelo y la persistencia
  actuales.
- `README.md`, `docs/import-contract.md` y
  `docs/installation-and-operation.md`.

No se inspecciona, copia ni describe ninguna fila, nombre, identificador,
captura, base de datos o XLSX operativo. La existencia local de archivos bajo
`data/private/` no se trata como evidencia autorizada del contrato del formato.

## Hechos confirmados por el repositorio

### Capacidad estructural del XLSX

1. El lector genérico acepta archivos `.xlsx` y usa `openpyxl` en modo de solo
   lectura y con valores, no fórmulas.
2. El lector devuelve filas asociadas a sus cabeceras y puede validar cabeceras
   vacías o duplicadas, anchura de filas, columnas requeridas y vacíos en
   columnas configuradas como obligatorias.
3. Los contratos de columnas de progreso son configurables por quien adapta la
   fuente. No declaran nombres oficiales de cabeceras ADAMS.
4. El adaptador provisional no asigna escala, rango, redondeo ni semántica
   acumulativa al valor de progreso. Su documentación declara desconocidos el
   nombre del informe, hoja, cabeceras, valores vacíos, sentinelas y formato
   real.
5. Los diagnósticos y la procedencia están diseñados para no guardar filas
   completas ni valores personales innecesarios.

Estos hechos describen la capacidad del lector, no la estructura del informe
real. En particular, el repositorio no confirma nombre de hoja, orden de
columnas, número de columnas, encabezados, separadores de bloques ni regla de
fin de bloque del XLSX de evolución.

### Identidad y dependencia de #110

1. El contrato aprobado de #110 usa `Usuario` como DNI estable del alumno;
   `Apellidos` y `Nombre` forman el nombre visible normalizado.
2. El operador selecciona una edición existente; el snapshot de #110 no crea
   cursos ni ediciones automáticamente.
3. El dominio distingue `Student`, `Edition` y `Enrollment`. La matrícula es
   la pertenencia de un alumno a una edición.
4. La resolución por nombre o correo no está permitida: el contrato de
   identidad externa establece que nombres y correos son evidencia descriptiva,
   no claves de matching.
5. La aplicación actual contiene tablas y repositorios para alumnos,
   ediciones y matrículas, y el importador de progreso actual exige que la
   matrícula exista. Esto confirma una dependencia de ejecución respecto de
   #110; no confirma que una base local concreta contenga todas las matrículas
   necesarias.

Para #112, la identidad mínima aprobada es el identificador estable que permita
resolver la matrícula existente de #110 (DNI del alumno más la edición ya
seleccionada, o una referencia estable de matrícula si el contrato del formato
la aporta). No se puede escoger entre esas formas para el XLSX real sin
confirmar su columna o combinación de columnas.

### Modelo de contenido y estado actual existentes

1. `ContentNode` admite tipos `MODULE`, `SUBMODULE` y `ELEMENT`, con padre
   obligatorio para submódulos y elementos, y no crea la jerarquía por sí solo.
2. `ContentProgressSnapshot` representa explícitamente una observación fechada
   y append-only de progreso de una matrícula sobre un nodo.
3. La tabla actual `content_progress_snapshot` contiene
   `enrollment_id`, `node_id`, `captured_at`, `progress_percentage` y un
   `external_id` opcional.
4. Existe un índice único sobre matrícula, nodo, fecha de captura y porcentaje.
   Por tanto, una observación repetida puede resultar unchanged, pero un valor
   distinto o una fecha distinta forma otra observación histórica.
5. El dominio valida el porcentaje de progreso de los snapshots entre 0 y 100,
   inclusive, pero el adaptador provisional no afirma que el valor fuente tenga
   esa escala. Son dos fronteras distintas y no deben confundirse.

## Decisiones aprobadas para el diseño de #112

Estas reglas proceden del plan aprobado del Issue; todavía requieren contrato
del formato real antes de implementarse:

- Procesar por bloques de alumno y producir preview, diagnósticos y resumen
  antes de una confirmación humana.
- Aplicar solamente módulos 1, 2, 3 y 4 y sus submódulos con convención
  `módulo + número romano` (`1.I`, `1.II`, `2.I`, etc.).
- Excluir `Presentación`, `Resumen`, `Caso práctico final`, actividades,
  evaluaciones y cualquier contenido que no cumpla esa convención.
- No inventar nodos, títulos, jerarquías ni identificadores que no estén
  respaldados por el contrato confirmado.
- En la primera importación crear solamente la estructura permitida; en las
  siguientes hacer upsert del estado actual, sin duplicados.
- Una ausencia posterior conserva el último estado conocido; no significa cero,
  borrado, no iniciado ni retroceso.
- La fecha de importación es la última actualización del estado actual.
- Validar el porcentaje de páginas visualizadas en el rango inclusivo 0--100.
- Mantener el porcentaje global de la columna G separado del porcentaje de
  páginas visualizadas; no calcular uno a partir del otro.
- No conservar histórico de snapshots de progreso para este flujo.
- Mantener la importación local, transaccional, idempotente y condicionada a
  confirmación humana, sin generar ni enviar comunicaciones.

## Evidencia ausente y bloqueo explícito

No hay en el repositorio una especificación oficial ni una muestra
anonimizada/autorizada del XLSX que confirme los puntos siguientes:

| Área | No confirmado |
| --- | --- |
| Identidad | Cabecera exacta, estabilidad, combinación con edición y regla para bloques sin identificador explícito. |
| Bloques | Marcador de inicio, delimitador, filas de cabecera repetidas, regla de fin y asociación de cada fila al alumno. |
| Columnas | Nombres exactos, posiciones, hoja, anchura y si existe una columna G estable. |
| Vacíos | Diferencia entre celda vacía, cero, `N/A`, texto localizado, fórmula sin valor y ausencia de fila. |
| Duplicados | Si una repetición es error, varias observaciones, actualización o conflicto; no hay política respaldada por formato real. |
| Columna G | Nombre, unidad, escala, semántica, granularidad y si es global por alumno, bloque o informe. |
| Progreso | Si el valor es páginas visualizadas, porcentaje, fracción, contador, estado o acumulado. |
| Contenido | Títulos, identificadores estables, orden y relación real entre módulos y submódulos. |

En consecuencia, no se puede afirmar todavía el contrato estructural del XLSX
real, ni aceptar como importable una fila real, ni definir una conversión de
vacíos/duplicados/columna G. El bloqueo no se resuelve usando nombres o
posiciones plausibles: hacerlo inventaría semántica, incumpliría el plan y
podría asociar progreso a otra matrícula.

## Contenido importable y exclusiones: estado de la especificación

El conjunto importable está **aprobado como regla de alcance**, pero no está
confirmado en un XLSX real. Cuando exista evidencia autorizada, una fila solo
podrá ser candidata si su contenido satisface simultáneamente:

1. pertenece a una matrícula ya resuelta por identidad estable;
2. identifica un módulo 1--4 o un submódulo con patrón módulo+número romano;
3. aporta valores cuya columna y escala estén confirmadas; y
4. no pertenece a una de las categorías excluidas.

Todo lo demás debe producir exclusión o diagnóstico seguro, no inferencia.
Las exclusiones aprobadas son `Presentación`, `Resumen`, `Caso práctico
final`, actividades, evaluaciones y contenido fuera de módulo 1--4 o fuera del
patrón de submódulo. La evidencia disponible no permite afirmar cómo se
representan textualmente esas categorías en el XLSX.

## Auditoría de incompatibilidad de persistencia

El requisito aprobado de #112 es **estado actual por matrícula y contenido**:
upsert, última actualización de la importación, conservación ante ausencia y
sin snapshots históricos. El estado actual del repositorio es diferente:

- `ContentProgressSnapshot` se documenta y valida como observación histórica,
  fechada y append-only.
- Su clave lógica actual incluye fecha de captura y porcentaje, por lo que no
  identifica una única fila mutable por matrícula y nodo.
- `ProgressImportService` requiere `recorded_at` y escribe snapshots; no
  implementa conservación por ausencia como estado actual ni almacena por
  separado la columna G.
- La tabla actual no contiene un campo para el porcentaje global de G ni una
  marca que distinga páginas visualizadas de ese porcentaje.

Usar `ContentProgressSnapshot` sin cambiar su semántica incumpliría el plan:
crearía histórico y no permitiría un upsert inequívoco del estado actual.
Cambiar silenciosamente su significado también rompería la documentación y
los consumidores que esperan observaciones históricas.

### Alternativas consideradas

1. **Reutilizar `ContentProgressSnapshot` como estado actual.** Menor cambio,
   pero incompatible con append-only, con la clave por fecha/valor y con el
   requisito de no conservar snapshots. Se descarta.
2. **Añadir una entidad/tabla específica de estado actual.** Una fila por
   matrícula y nodo, con progreso de páginas, fecha de importación y un campo
   independiente para G cuando su contrato esté confirmado. Permite upsert,
   ausencia conservadora e idempotencia sin alterar el histórico existente.
3. **Mantener un modelo de estado actual fuera de SQLite.** Evita migración,
   pero no ofrece persistencia durable, consulta uniforme ni transacción con la
   revisión/aplicación local. No es adecuado para el requisito operativo.

### Recomendación no implementada

Recomiendo la alternativa 2: una representación específica de estado actual,
separada de `ContentProgressSnapshot`, con identidad única por matrícula y
nodo, fecha de importación y campos separados para páginas visualizadas y G.
La entidad exacta, nombres de columnas, restricciones, migración y relación
con `ContentNode` requieren aprobación de diseño después de confirmar el
formato real. Este documento no crea nada de ello.

## Criterios de parada antes de una implementación funcional

El trabajo debe detenerse y volver a planificación si no se obtiene evidencia
autorizada y aprobación explícita para:

1. cabeceras/hoja y contrato estructural del XLSX;
2. identidad estable y su resolución contra matrículas existentes de #110;
3. inicio, fin y asociación de bloques;
4. representación de vacíos y política de duplicados;
5. nombre, unidad y escala de G;
6. semántica y rango del porcentaje de páginas visualizadas;
7. identificadores y jerarquía confirmados de módulos/submódulos;
8. decisión de persistencia de estado actual separada del snapshot histórico.

La dependencia #110 debe seguir disponible en el entorno de ejecución: edición,
alumnos y matrículas han de existir antes de aplicar progreso. Si la identidad
del XLSX no puede resolver una matrícula existente, el bloque se rechaza y no
se crea ninguna entidad. La ausencia de #110, una decisión de persistencia
materialmente distinta o evidencia que cambie el alcance obliga a parar y
solicitar replanteamiento.

## Validación de esta fase

- Revisión documental cruzada de Issue #112, Issue #110 y las fuentes listadas:
  realizada sin consultar ni copiar datos operativos.
- Auditoría del modelo y esquema actual: realizada; confirma la divergencia
  entre `ContentProgressSnapshot` histórico y el estado actual requerido.
- Revisión de privacidad: no se añaden XLSX, filas, PII, bases, credenciales
  ni fixtures operativos.
- Tests de contrato abstracto: no se añaden; la evidencia del formato real es
  insuficiente y no se deben inventar cabeceras o semánticas.
