# Ficha de alumno

La ficha se selecciona por `enrollment_id`, no por un nombre. La vista presenta
el resumen de progreso, evaluaciones, alertas, historial y comunicaciones
sugeridas de esa matrícula.

Las acciones del tutor se guardan en la tabla `tutor_action`, separada de las
tablas de identidad (`student`) y de los registros provenientes de ADAMS. La
base operativa se crea bajo `data/local/`, una ruta ignorada por Git. Los datos
que aparecen en la aplicación y en las pruebas son sintéticos; no se incluyen
exportaciones ni datos personales reales.
