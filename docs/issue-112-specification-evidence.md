# Issue #112: especificación y evidencia del formato de evolución

## Propósito y límite de este documento

Este documento conserva la evidencia de contrato que autorizó la implementación
del Issue #112. No contiene la muestra, filas, valores personales ni una copia
del XLSX operativo; tampoco es un fixture de pruebas.

### Registro de autoridad de la muestra

- **Autoridad:** responsable funcional del flujo ADAMS, mediante la muestra
  autorizada entregada por el canal local/privado operativo.
- **Fecha de revisión del contrato:** 2026-09-18.
- **Referencia no sensible:** `adams-evolution-xlsx-contract-v1`.
- **Custodia:** la muestra permanece fuera del repositorio, bajo
  `data/private/` ignorado y acceso operativo restringido. No se usa como
  fixture ni se copia a documentación, logs o Issues.

La implementación se limita a las propiedades estructurales y semánticas
registradas abajo. Cualquier columna o fila fuera de ellas sigue siendo
desconocida y no se importa.

La regla de esta auditoría es separar lo confirmado por la muestra autorizada,
lo aprobado para el diseño y lo que sigue sin evidencia. La referencia anterior
identifica la autorización, pero no permite reconstruir la muestra.

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

## Vía de autorización y custodia de evidencia

La evidencia necesaria para desbloquear una implementación funcional debe
seguir una vía de autorización explícita, separada del repositorio:

1. El responsable funcional solicita una muestra mínima del formato y define
   qué campos son necesarios para confirmar el contrato.
2. El propietario autorizado de la fuente confirma que la muestra puede ser
   utilizada para análisis técnico y que ha sido anonimizada o sintetizada
   suficientemente antes de compartirla con el equipo de desarrollo.
3. La muestra autorizada se entrega únicamente por el canal local o privado
   aprobado para datos operativos. No se copia a Git, Issues, Pull Requests,
   logs, capturas ni documentación versionada.
4. La custodia permanece en almacenamiento local ignorado, con acceso limitado
   al personal autorizado. El repositorio conserva solo conclusiones
   estructurales, códigos de diagnóstico y decisiones aprobadas, nunca filas,
   nombres, identificadores, valores personales ni el archivo fuente.
5. Tras la revisión, se registra una referencia no sensible a la evidencia
   (por ejemplo, fecha de revisión, responsable y versión del contrato), sin
   incluir la muestra ni permitir reconstruirla. La retención y eliminación de
   la copia local siguen la política operativa aplicable.

Una descripción o decisión aprobada por sí sola no prueba que el XLSX real
cumpla el contrato. Si no puede obtenerse una muestra autorizada, debe
documentarse la ausencia de evidencia y mantenerse el bloqueo; no se permite
suplirla con una exportación local no autorizada ni con hipótesis sobre
cabeceras o posiciones.

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

## Decisiones finales M1--M5 y comprobación de implementación

Estas decisiones son parte del plan final y no son cuestiones abiertas:

| Decisión | Reflejo explícito | Cobertura verificable |
| --- | --- | --- |
| **M1 Custodia/evidencia** | La evidencia autorizada se identifica como `adams-evolution-xlsx-contract-v1`, permanece en `data/private/` ignorado y no se usa como fixture, log ni documentación reproducible. | Este registro de custodia y `git check-ignore`/auditoría de seguridad; los tests crean únicamente XLSX sintéticos bajo `tmp_path`. |
| **M2 Lector genérico/adaptador** | `read_xlsx_values` solo lee filas estructurales; `evolution_xlsx` interpreta bloques, identidad, alcance y porcentajes. Ninguna capa genérica conoce el dominio de evolución. | `tests/unit/test_evolution_xlsx.py` ejercita el adaptador con workbook sintético y la suite existente de `tabular_import` conserva la frontera estructural. |
| **M3 API operativa preview/apply** | `import_evolution_xlsx(..., confirm=False)` es preview sin escritura y `confirm=True` es apply tras confirmación humana. Es la interfaz operativa reproducible; UI y CLI adicional quedan fuera de alcance. | Las pruebas de preview, apply, idempotencia y consistencia del plan verifican ambas rutas. |
| **M4 Contadores/auditoría no solapados** | `changed`/`unchanged` cuentan cambios de estado global o de contenido; `rejected` y `excluded` cuentan diagnósticos separados. `import_batch_change` conserva una entrada por diagnóstico o cambio, sin filas fuente ni PII. | Las pruebas de contadores, exclusiones, cambios globales y privacidad comprueban categorías y mensajes no identificables. |
| **M5 Mensajes privacy-safe** | Los diagnósticos solo exponen códigos, fila y mensajes genéricos; nunca el identificador, nombre, correo o fila completa. | `test_apply_keeps_diagnostics_private_and_records_global_changes` y las comprobaciones de seguridad del repositorio lo verifican. |

La aplicación atómica también está comprobada: una prueba sintética fuerza un
fallo durante `apply` y verifica que se revierten estado, estructura y toda la
auditoría del lote.

## Contrato confirmado por la muestra autorizada

La revisión `adams-evolution-xlsx-contract-v1` confirmó: una hoja activa con
bloques iniciados por `Usuario`, la identidad estable en esa celda, la columna
G titulada `Evolución`, porcentajes expresados como valores 0--100 (incluidos
0 y 100), y filas de contenido con módulos `Módulo 1` a `Módulo 4` o
submódulos con módulo y número romano. La fecha de importación es la fecha de
actualización del estado local. Los nombres visibles no se usan para resolver
matrículas.

La muestra no autoriza inferencias sobre actividades, evaluaciones, filas fuera
del patrón, vacíos, duplicados o semánticas distintas de las anteriores; esas
entradas se excluyen o diagnostican sin transformación silenciosa.

## Evidencia aún ausente y límites explícitos

La evidencia autorizada no confirma los puntos siguientes:

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

En consecuencia, el importador no acepta esas variantes: las diagnostica o las
excluye. No usa nombres ni posiciones como heurística de identidad y nunca
registra filas completas. Las decisiones M1--M5 anteriores describen el
tratamiento aprobado de custodia, arquitectura, operación y privacidad; no
convierten variantes no evidenciadas en semántica del dominio.

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

## Decisión de persistencia implementada

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

Por ello, la implementación usa `content_progress_current` y
`enrollment_progress_current` para estado actual, y deja
`ContentProgressSnapshot` sin modificar como histórico. Las tablas son únicas
por matrícula/contenido o matrícula, conservan ausencias, separan G y páginas,
y actualizan `imported_at` con la fecha del lote. Cambiar esta decisión
requeriría replanteamiento; no es una tarea pendiente de #112.

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

### Decisión adoptada

Se adopta la alternativa 2: una representación específica de estado actual,
separada de `ContentProgressSnapshot`, con identidad única por matrícula y
nodo, fecha de importación y campos separados para páginas visualizadas y G.
La implementación concreta está en el esquema y en `evolution_xlsx.py`; no
modifica la semántica histórica existente.

### Matriz de decisiones pendientes

| Decisión | Hecho disponible | Decisión requerida | Evidencia/autorización necesaria | Estado |
| --- | --- | --- | --- | --- |
| Identidad y resolución de matrícula | #110 exige una identidad estable y una matrícula existente | Confirmar la cabecera o combinación que vincula cada bloque con `Enrollment` | Muestra autorizada y aprobación del contrato de identidad | Pendiente; bloquea implementación |
| Bloques de alumno | El lector genérico puede devolver filas, pero no conoce bloques ADAMS | Confirmar inicio, fin, repetición de cabeceras y asociación de filas | Muestra autorizada del formato, sin PII | Pendiente; bloquea parser |
| Hoja y columnas | No hay nombres oficiales confirmados en el repositorio | Confirmar hoja, cabeceras, posiciones y anchura | Contrato estructural autorizado | Pendiente; bloquea mapeos |
| Vacíos y duplicados | El dominio no define su semántica de origen | Decidir tratamiento de vacío, cero, sentinelas, fórmulas y repetición | Ejemplos sintéticos representativos o evidencia autorizada | Pendiente; bloquea normalización |
| Columna G | Se requiere separarla del progreso de páginas | Confirmar nombre, unidad, escala y granularidad | Evidencia autorizada y decisión funcional | Pendiente; bloquea persistencia |
| Progreso de páginas | El dominio acepta 0--100, pero la fuente no está confirmada | Confirmar semántica, unidad y rango de la fuente | Contrato autorizado | Pendiente; bloquea validación funcional |
| Contenido y jerarquía | `ContentNode` soporta módulos, submódulos y elementos | Confirmar identificadores, títulos y jerarquía importables | Catálogo/contrato autorizado; no inferencia por título | Pendiente; bloquea creación de estructura |
| Estado actual frente a histórico | `ContentProgressSnapshot` es fechado y append-only | Usar tablas específicas para upsert actual, ausencias conservadoras y última actualización | Decisión M1--M5 y esquema implementado | Resuelto |
| Fecha de actualización | El plan propone la fecha de importación | Confirmar que no se usará una fecha inventada del informe | Aprobación del contrato funcional | Pendiente; bloquea modelo final |
| Confirmación y transacción | El plan exige preview, confirmación e idempotencia | Confirmar el límite exacto entre preview y aplicación | Decisión de flujo aprobada | Pendiente; bloquea servicio |

Ninguna fila de esta matriz autoriza por sí misma una implementación. Las
decisiones que afecten arquitectura, persistencia o semántica deben aprobarse
después de recibir evidencia autorizada; hasta entonces permanecen pendientes.

## Estado factual del PR #117

La consulta factual actual de GitHub muestra que el PR #117 está **MERGED**
(merge registrado el 17 de septiembre de 2026), con un único commit que añade
este documento. No constan reviews publicados, comentarios del PR ni checks en
el estado consultado. Por tanto, el texto del cuerpo del PR que afirma
`READY FOR HUMAN REVIEW` y `APPROVE FOR HUMAN REVIEW` no constituye evidencia
de una validación o revisión independiente registrada.

No se ha encontrado en la información pública consultada un registro que
permita afirmar literalmente los estados `NOT READY` del Validator o
`REQUEST CHANGES` del Reviewer para el PR #117. Esos estados no deben
inventarse ni atribuirse retrospectivamente. La conclusión documental segura
es que el expediente publicado carece de evidencia verificable de esas dos
decisiones y que el PR, al estar ya fusionado, no puede tratarse ahora como un
PR abierto pendiente de validación/revisión. Esta discrepancia debe quedar
resuelta por el responsable del flujo antes de usar el PR #117 como precedente
de cumplimiento.

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
