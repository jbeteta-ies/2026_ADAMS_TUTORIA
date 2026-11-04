# Navegación declarativa segura

La navegación declarativa de esta Issue es un contrato versionado de pasos
ordenados. Cada paso contiene `GET` o `POST`, URL, `params`, `form_data`, un
timeout acotado y una señal de resultado (`status_code`, `url_path` o
`text_marker`). El origen es una allowlist obligatoria y el máximo es de 20
pasos, con timeout entre 1 y 120 segundos.

El ejecutor solo realiza navegación. No ofrece click, fill, JavaScript,
descubrimiento de enlaces, scraping, descarga de respuestas ni acciones de
contenido. Las acciones no declaradas no existen (deny-by-default). `POST` se
acepta únicamente como paso explícito del contrato con `read_only: true`. La
ausencia de esa declaración se rechaza (deny-by-default). Esta marca no
garantiza que el servidor trate el POST como lectura ni puede detectar una
mutación remota: solo exige autorización explícita del operador para intentar
el paso. No se ejecutan acciones mutantes en esta aplicación.

## Sesión y seguridad

`NavigationExecutor` recibe un `LoginSession` ya autenticado en memoria. La
sesión sigue siendo propiedad del flujo de login y debe cerrarse por su dueño.
No se copian ni persisten credenciales, cookies, tokens, perfiles, HTML,
capturas o PII. Los diagnósticos son códigos (`timeout`, `session_expired`,
etc.) y nunca incluyen URL completa, cabeceras, cuerpos o excepciones.

Un campo CSRF puede declararse mediante `csrf_field`; se lee del input oculto
de la página actual y se envía solo en ese POST. No se ejecuta JavaScript para
obtener campos dinámicos. Si el sitio exige JavaScript, un DOM cambiante,
redirecciones fuera del origen, CAPTCHA o MFA, el flujo se detiene y requiere
validación/intervención humana.

## Piloto ADAMS futuro

El piloto autorizado queda limitado a reutilizar el login existente, seleccionar
un aula/curso y verificar llegada a una página objetivo. Los valores reales se
proporcionarán solo localmente en una configuración ignorada por Git. En esta
Issue no se ejecuta el piloto, no se usan credenciales reales y no se incluyen
URLs o identificadores operativos. Antes de autorizarlo, el operador debe
validar en un entorno autorizado CSRF, JavaScript, campos dinámicos,
redirecciones, expiración de sesión y señales estables de éxito.

CAPTCHA/MFA no se sortea. La cancelación es cooperativa mediante `Event`; un
timeout, error, sesión expirada o señal no confirmada detiene la secuencia.

## Plantilla YAML

`config.yaml.example` incluye, dentro del elemento sintético de `sites`, una
única plantilla comentada de tres pasos post-login: GET de preparación, POST de
selección y GET de llegada a la página objetivo. Incluye `allowed_origin`,
`params`, `form_data`, `aula`, `modoCarga`, `ssl`, `csrf_field`,
`timeout_seconds`, `read_only: true` para el POST y `expected_result`. `login_url` y los campos de login siguen
siendo propiedades del sitio y no forman parte de `navigation`. Todos los
valores de origen, rutas, campos y marcadores son placeholders y no describen
el sitio real.

El cargador valida `navigation` anidada en cada sitio y la convierte a un
`NavigationPlan` en memoria. Un sitio debe declarar exactamente uno de
`target_url` (compatibilidad con la navegación simple existente) o
`navigation`; declarar ambos es ambiguo y se rechaza. La plantilla comentada de
`config.yaml.example` muestra la forma segura sin alterar el `config.yaml`
local. El monitor reutiliza la sesión que devuelve el login y ejecuta el plan
después del login y en cada recarga. No se debe copiar ningún valor de sesión al
YAML.

`csrf_field` es únicamente el nombre del input oculto; el token se obtiene en
memoria de la página actual para el POST cuando corresponda. Si el sitio exige
JavaScript, campos dinámicos no observables por este contrato, CAPTCHA, MFA o
redirecciones fuera de `allowed_origin`, no se debe completar la plantilla para
sortearlos: el flujo debe detenerse y requerir intervención/validación humana.
