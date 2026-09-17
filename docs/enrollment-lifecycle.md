# Ciclo de vida auditable de alumnos y matrículas

`EnrollmentLifecycleService` aplica candidatos ya normalizados dentro de una
transacción SQLite. La identidad de alumno es `(source, context,
source_student_id)` y la identidad de matrícula añade la edición y el
identificador externo de matrícula. Nunca se resuelve por nombre o correo.

Cada ejecución se asocia a un `ImportBatch`, que admite `scope_type=partial` o
`scope_type=full`. Un lote completo exige `scope_reference` (la edición
existente) y las claves de matrícula que no aparecen se marcan como ausentes y
se desactivan lógicamente. Un lote parcial no produce bajas por ausencia.
La aplicación solo acepta lotes en estado `pending` o `confirmed`, de acuerdo
con el contrato de importación; los estados terminales (`applied`, `rejected` y
`failed`) no pueden volver a aplicarse.

Las bajas no eliminan filas. El estado actual se mantiene en
`enrollment_state` y cada evento se añade a `student_history` o
`enrollment_history`; `import_batch_change` proporciona el vínculo operativo
con el lote. En importaciones generales la reactivación requiere
`action="reactivate"`; los snapshots completos reactivan automáticamente la
matrícula que vuelve a aparecer.

En un lote `full`, una clave compuesta determinable a partir del candidato se
registra como presente antes de validar sus atributos. Por eso un conflicto
queda presente/indeterminado y no provoca una baja. Las bajas reales se trazan
con un cambio `absent` de `import_batch_change`, con
`diagnostic_code=absent_from_full_scope` y `source_row_number=NULL`, porque no
existe fila de origen para una ausencia.

Los datos descriptivos del alumno se tratan como evidencia de identidad, no
como una clave de matching: si nombre o correo no nulos contradicen lo ya
registrado, el candidato queda en `conflict` y no se modifica el alumno. Solo
se completa un dato descriptivo que estuviera ausente, registrando el evento
`modified` en `student_history`.
Esta regla mantiene la misma semántica que `ExternalIdentityResolver`: un
correo nuevo no completa un correo almacenado como `NULL`; se registra como
conflicto, porque el correo solo es evidencia descriptiva y no una clave de
identidad.

El `idempotency_key` de `ImportBatch` es único cuando se proporciona. Las
tablas de identidad y las transacciones impiden duplicados y dejan la
operación en un estado completo o revertido. `action` y `group` son opcionales
y no intervienen en la resolución de identidad. Course y Edition se crean y
mantienen manualmente: esta capa solo referencia ediciones existentes. Si una
clave de matrícula ya pertenece a otro alumno, el candidato queda en conflicto
(`enrollment_student_mismatch`) y no se crea ni reasigna ninguna matrícula.

Esta funcionalidad no parsea Excel, no crea cursos/ediciones, no procesa
evaluaciones ni progreso y no incluye interfaz de usuario. Las pruebas y
ejemplos deben usar siempre datos sintéticos; la base operativa permanece en
almacenamiento local ignorado.

`StudentReconciliationService` es la frontera de aplicación para el contrato
`StudentRecord` de la hoja de alumnos. Recibe la edición seleccionada
manualmente, la convierte en candidatos de matrícula y delega toda la
resolución y persistencia en `EnrollmentLifecycleService`. Una edición ausente
falla antes de escribir; los registros sin identidad estable no se emparejan
por nombre o correo.

## Snapshot completo por edición

`prepare_snapshot_xlsx` recibe un XLSX completo y la edición existente elegida
por la persona operadora. Siempre crea un lote con `scope_type=full` y esa
edición como `scope_reference`; no existe una ruta de snapshot parcial ni se
lee la edición desde el archivo. `Usuario` (DNI) es la identidad estable y
`full_name` se normaliza como `Apellidos + Nombre`.

El preview separa altas, cambios de nombre, bajas lógicas, reactivaciones, sin
cambios y rechazos o conflictos. Las filas ausentes solo desactivan matrículas
de la edición seleccionada. Una aparición posterior reactiva la misma fila de
matrícula, conservando sus IDs; nunca se borran físicamente alumnos,
matrículas ni histórico. Las columnas no pertenecientes al contrato se
ignoran.

La confirmación requiere revisión explícita y aplica el snapshot completo en
una única transacción. La clave formada por la huella del archivo y la edición
evita repetir el mismo lote: repetir preparación o confirmación no crea
duplicados ni nuevos eventos espurios. Si falla cualquier parte, SQLite revierte
el lote completo; solo queda, cuando es posible, un registro seguro del fallo.
