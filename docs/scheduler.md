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

El modo `adams-monitor --site <id> --once-window` crea un worker de un solo
sitio. Espera antes del inicio, conecta dentro de la ventana y termina al
alcanzar `EXIT`; si comienza después del límite no realiza login ni inicia una
segunda ventana. `SIGINT` y `SIGTERM` solicitan el mismo cierre cooperativo.
La opción `--once-window` requiere `--site`; si se omite, la CLI devuelve el
código de configuración `2` antes de crear el monitor.

## Monitorización multi-sitio

`adams_tutoria.monitoring.MultiSiteMonitor` conecta esos eventos con el
adaptador indicado por `provider`. Cada sitio obtiene un contexto de navegador
efímero propio, inicia sesión al entrar en su ventana y recarga únicamente su
`target_url` en el intervalo configurado. `timeout_seconds` limita cada
 navegación. `max_retries` es el número de reintentos posteriores al primero:
 `0` hace un intento y `2` permite hasta tres intentos totales, tanto para
 login como para cada recarga. Un error, bloqueo o timeout solo desactiva el
 sitio afectado.

Al producirse `EXIT`, o al llamar a `close()`, se cierran el contexto y el
navegador del sitio. El motor no ejecuta acciones de contenido, no persiste
sesiones, cookies, tokens ni HTML, y sus eventos contienen solo el identificador
del sitio y estados operativos seguros.

## Logs locales por sitio

Los eventos de `startup`, `login`, `navigation`, `reload`, `retry` y `exit` se escriben en el `log_file` configurado para
cada sitio como una línea JSON con `timestamp`, `site_id`, `provider`, `action`
y `result`. Los errores solo usan el diagnóstico fijo `operation failed`; no se
copian excepciones, URLs, respuestas, HTML, cabeceras, cookies, tokens,
credenciales ni datos de estudiantes.

Cada fichero rota al alcanzar 1 MiB y conserva como máximo tres copias rotadas.
La limpieza elimina ficheros con más de 30 días. Los logs viven bajo
`data/local/`, ignorado por Git; `config.yaml` también permanece ignorado y no
debe recrearse en el repositorio.

Si el destino no puede escribirse, el monitor emite un evento de error seguro
para ese sitio y continúa procesando los demás sitios. El fallo del logger no
propaga excepciones al ciclo de monitorización.

## Suspensión, reintentos y diagnóstico

El bucle consulta el reloj en cada iteración. Tras una suspensión del equipo no
reproduce los intervalos vencidos: la siguiente consulta solo produce la
transición que corresponda a la hora actual. Si la ventana ya terminó, produce
`EXIT` y cierra la sesión; si sigue activa, permite como máximo una recarga en
esa iteración y recalcula el siguiente intervalo.

`max_retries` cuenta reintentos adicionales al intento inicial. Los fallos
recuperables se registran con acción `retry` y respetan el límite de la ventana.
El backoff predeterminado es finito y está limitado a 30 segundos; una prueba
puede inyectar una política y un reloj de espera sin cambiar el YAML. Los
valores inyectados negativos, infinitos, NaN o no numéricos se convierten en
espera cero; los valores positivos excesivos se acotan a 30 segundos.
CAPTCHA, MFA, bloqueo y caducidad de sesión no se reintentan automáticamente.
El cierre normal de una ventana se registra como acción `exit`, separado de los
errores de navegación o autenticación.

Una respuesta `human_intervention_required` es un bloqueo terminal: no se
considera login correcto, no genera una sesión activa y no dispara reintentos ni
otra acción automática. Este comportamiento está cubierto por una prueba con
un sitio y credenciales sintéticos.

La línea `response_metadata.expected_result_match: not_checkable` significa que
no había una señal de respuesta evaluable en ese paso (por ejemplo, una
respuesta no disponible o sin el atributo comprobable); no demuestra por sí
sola que la sesión haya caducado. Tanto `expected_result_not_confirmed` como
`not_checkable` son resultados terminales del monitor: no se reintentan ni se
reinterpretan como `session_expired`. La navegación conserva el diagnóstico
seguro del paso para distinguirlo de `session_expired`, bloqueo o una validación
no confirmada.

## Validación manual de una ventana nocturna

Con un sitio sintético y un log local ignorado, comprobar en la zona horaria
configurada: (1) `ENTER` y login a las 22:50, (2) una recarga por intervalo
mientras la ventana está activa, (3) ninguna nueva entrada a las 00:00, (4)
`EXIT` exactamente a la 01:00 y cierre de sesión, y (5) ninguna petición
posterior. Esta comprobación requiere observar solo identificadores de sitio y
estados; nunca cookies, credenciales, tokens, cuerpos o datos personales.
