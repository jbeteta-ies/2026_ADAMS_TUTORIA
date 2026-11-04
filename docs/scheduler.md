# Planificador de ventanas por sitio

`adams_tutoria.scheduler` calcula únicamente si cada sitio debe estar activo.
No realiza login, recargas, navegación ni acciones sobre cursos.

Las ventanas usan la hora local del `timezone` configurado, con fecha de inicio
y fecha final inclusivas. La hora de inicio es inclusiva y la hora final es
exclusiva (`start_time <= hora < end_time`). Las ventanas que cruzan medianoche
(`start_time > end_time`) están permitidas: el tramo posterior a medianoche
pertenece al día de la semana en que comenzó la ventana. Una ventana con horas
iguales no es válida. Los días de semana se comparan con la fecha local del
sitio, salvo ese tramo posterior a medianoche, que conserva el día de inicio.

`SiteScheduler.tick()` emite eventos `ENTER`, `EXIT` o `INVALID`. La primera

`run_forever()` mantiene el ciclo continuo. Recibe `clock`, `wait`,
`on_events` y `should_stop` como dependencias opcionales inyectables, por lo
que las pruebas no dependen del reloj real ni esperan en tiempo real.
