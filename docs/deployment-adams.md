# Despliegue del worker ADAMS

El workflow `.github/workflows/monitor-adams.yml` ejecuta únicamente el sitio
`adams-site` en un runner Ubuntu efímero. Instala Python 3.13 y las dependencias
bloqueadas por `uv.lock`, valida los Secrets y genera la configuración efectiva
antes de instalar Chromium de Playwright. Solo después de esa validación puede
iniciarse el worker.

## Configuración inicial

En la configuración **Settings > Secrets and variables > Actions** del repositorio,
crear estos Secrets, sin escribir sus valores en el repositorio:

- `ADAMS_USERNAME`
- `ADAMS_PASSWORD`

El workflow comprueba que ambos estén presentes, genera `config.yaml` con
permisos privados a partir de `config.adams.yaml.template` y valida su esquema.
El fichero generado se elimina al terminar el job y nunca se sube como artefacto.
`config.yaml` permanece ignorado por Git. `config.example.yaml` es la plantilla
genérica local y `config.adams.yaml.template` es exclusivamente la plantilla
con forma de producción para ADAMS; no deben confundirse ni intercambiarse.

## Horario y ejecución manual

La programación es de lunes a viernes a las 16:20 en `Europe/Madrid`. El
worker aplica la ventana configurada de 16:20 a 20:40 y termina de forma
cooperativa al cerrarla. GitHub puede iniciar un `schedule` con retraso; el
workflow no debe considerarse un reloj exacto.

Para probarlo, abrir **Actions > Monitor ADAMS > Run workflow**. La primera
ejecución real requiere una ejecución manual supervisada con los Secrets ya
configurados.

La concurrencia `adams-site` evita solapamientos y no cancela una ejecución que
ya esté en curso. El límite del job permite completar la ventana con margen.

## Diagnóstico y suspensión

Los eventos estructurados del worker incluyen un `run_id` y se escriben en
`data/local/logs/`. Tras cada ejecución se intenta subir ese directorio como
artefacto, incluso si el worker falla, con una retención de 7 días. Los logs no
contienen credenciales, cookies, tokens, HTML ni la configuración efectiva.

En la página del workflow se puede abrir un run y descargar **Artifacts**. Para
detener temporalmente la automatización, deshabilitar el workflow desde el menú
de Actions; para reanudarlo, volver a habilitarlo. Una ejecución activa debe
dejarse terminar o cancelarse explícitamente desde GitHub.

Los runners son efímeros: no conservan sesiones, cookies, logs ni ficheros
locales entre ejecuciones. La ejecución real depende de la disponibilidad de
GitHub Actions, del sitio ADAMS y de la validez de los Secrets.
