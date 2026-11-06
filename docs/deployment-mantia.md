# Despliegue de Mantia en GitHub Actions

Este despliegue contiene dos workflows independientes y **solo manuales**:

- `Monitor Mantia 1`: `mantia1`, 14:30–16:30 (Europe/Madrid).
- `Monitor Mantia 2`: `mantia2`, 20:30–22:30 (Europe/Madrid).

Las fechas versionadas son las facilitadas para este curso (6–18 de noviembre
de 2026). Antes de cualquier activación definitiva hay que confirmar los días
lectivos. No hay ningún `schedule` activo en estos workflows.

## Seguridad y ejecución

El repositorio solo contiene `config.mantia.yaml.template`, con placeholders.
Cada ejecución lee los secretos `MANTIA_USERNAME` y `MANTIA_PASSWORD` de
GitHub Actions, genera un YAML temporal con permisos restringidos y lo valida
sin imprimirlo. El archivo temporal se elimina siempre. El monitor reutiliza el
adaptador Moodle existente, navega únicamente por los cuatro GET definidos en
la plantilla y finaliza con `--once-window`. El intervalo de recarga para el
despliegue es de 60 segundos.

Cada instancia tiene grupo de concurrencia, log y artifact propios. El tiempo
máximo del job está limitado a 155 minutos; los artifacts de diagnóstico se
conservan siete días. Los logs se publican antes de borrar el directorio local.
No se deben descargar ni compartir artifacts sin revisar que no contengan
información operativa innecesaria.

## Prueba supervisada antes de cron-job.org

La prueba real requiere intervención humana, secretos configurados y revisión
del artifact. No se considera realizada por los tests offline.
Esta prueba supervisada no es un requisito automatizado previo a presentar el
PR: es un gate humano posterior a la implementación y a la revisión, y debe
completarse antes de activar cron-job.org. No se ejecutan workflows reales ni
se accede a secretos como parte de la validación offline.

1. Confirmar que `MANTIA_USERNAME` y `MANTIA_PASSWORD` están configurados como
   secrets del repositorio y que no aparecen en ninguna salida.
2. Elegir una fecha y hora futura con la persona supervisora; no reutilizar
   una hora pasada. Para la prueba, preparar temporalmente una ventana de 15
   minutos e intervalo de 60 segundos en el workflow, sin activar horarios
   definitivos.
3. Ejecutar manualmente `Monitor Mantia 1` desde **Actions > Run workflow**.
4. Comprobar autenticación, las cuatro páginas GET, recargas periódicas y
   finalización automática al cumplirse los 15 minutos.
5. Revisar el artifact y confirmar ausencia de contraseñas, cookies, tokens,
   configuración efectiva y datos personales.
6. Repetir inmediatamente el procedimiento para `Monitor Mantia 2`.
7. Restaurar los valores versionados y conservar los enlaces/IDs de ejecución
   como evidencia operativa fuera del repositorio, sin incluir secretos.

Hasta completar esta prueba no se deben crear tareas en cron-job.org.

## Transferencia posterior a cron-job.org

Solo después de la prueba supervisada y de confirmar los días lectivos, una
persona autorizada puede crear **manualmente** dos tareas externas. Esta Issue
no crea, activa ni modifica tareas en cron-job.org.

Para cada instancia, usar una petición `POST` a la URL de dispatch del
repositorio:

```text
https://api.github.com/repos/OWNER/REPOSITORY/actions/workflows/monitor-mantia1.yml/dispatches
https://api.github.com/repos/OWNER/REPOSITORY/actions/workflows/monitor-mantia2.yml/dispatches
```

El cuerpo JSON es el mismo en ambos casos:

```json
{"ref":"main"}
```

La petición necesita un token de GitHub con el permiso mínimo para ejecutar
workflows. El token debe guardarse únicamente en el mecanismo seguro de
cron-job.org, nunca en el repositorio, en esta documentación o en los logs.
Usar el método `POST`, `Content-Type: application/json` y el encabezado
`Authorization: Bearer <TOKEN>` en la configuración privada de cron-job.org.
Configurar allí los días y horas confirmados, teniendo en cuenta que GitHub
Actions recibe la solicitud de forma externa; no añadir un `schedule` al YAML.

ADAMS no forma parte de este despliegue y sus workflows/configuración no se
modifican.
