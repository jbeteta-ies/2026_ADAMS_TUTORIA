# Reglas configurables de seguimiento

`adams_tutoria.follow_up` ofrece una capa interna independiente del origen de
datos. Su entrada está limitada a `Enrollment`, `ProgressSnapshot` y
`Evaluation`, y devuelve `FollowUpAssessment` con razones explicables.

## Configuración

Las reglas se suministran desde la configuración de la aplicación o desde una
fuente externa mediante `FollowUpRules.from_mapping`. No hay valores por curso
ni identificadores de evaluaciones incorporados en el evaluador. El mapping
requiere:

```python
{
    "not_started_max_progress": "0",
    "inactivity_after_hours": 168,
    "completion_min_progress": "100",
    "flag_pending_evaluations": True,
}
```

Los porcentajes son valores ya existentes en `ProgressSnapshot`; no se
calculan, agregan, ponderan ni interpretan elementos del curso ni puntuaciones
de evaluaciones. La escala del porcentaje debe ser la establecida por el
contrato interno, y los valores de ejemplo son solo sintéticos.

## Evaluación

`assess_follow_up(..., as_of=...)` exige una fecha explícita y con zona horaria.
Selecciona el snapshot más reciente que pertenezca a la matrícula y no sea
posterior a `as_of`. El intervalo de inactividad se compara usando timestamps
con zona horaria.

Se producen estas razones:

- `not_started`: el último porcentaje disponible está dentro del umbral
  configurado de no iniciado. Esta regla tiene precedencia sobre `inactive`:
  un snapshot antiguo dentro de este umbral solo produce `not_started`.
- `inactive`: la última observación no alcanza finalización y tiene una
  antigüedad igual o superior al intervalo configurado.
- `pending_evaluations`: existe al menos una evaluación con estado pendiente.
  No se calcula aprobado ni se interpreta una puntuación.
- `completed`: el porcentaje existente alcanza el umbral de finalización.
- `progress_unknown`: no existe un snapshot aplicable. Es una señal
  conservadora para revisión, no una afirmación de que el alumno no haya
  iniciado.

La finalización por sí sola no requiere seguimiento, pero puede coexistir con
`pending_evaluations`. Los datos faltantes no se convierten silenciosamente en
cero. La antigüedad se calcula para snapshots de progreso, mientras que las
evaluaciones pendientes se consideran por matrícula sin una ventana temporal;
por tanto, ambas reglas tienen una asimetría temporal deliberada.

## Resumen por matrícula

`adams_tutoria.summary.summarize_enrollment` compone un `EnrollmentSummary`
inmutable para una única matrícula. Recibe `as_of` de forma obligatoria y no
usa la hora actual del sistema. Aísla snapshots y evaluaciones por matrícula,
selecciona el último snapshot aplicable y expone su instante como
`last_progress_at`; ese campo representa progreso observado, no el último
acceso o login.

El resumen separa estados pendientes/completados de resultados explícitos
(`passed=True` o `False`). No calcula aprobados o suspensos a partir de
puntuaciones. El `FollowUpAssessment` se recibe ya calculado y se conserva en
el DTO; el resumen no vuelve a aplicar las reglas de seguimiento.
