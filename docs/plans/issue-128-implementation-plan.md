# Plan de implementación revisado: Issue #128

## Objetivo

Proporcionar un comando CLI reproducible para ejecutar **un único intento** de
login en ADAMS, cargando configuración local desde `.env` cuando exista y
comunicando solamente un estado operativo seguro.

## Alcance

- Declarar `python-dotenv` como dependencia de ejecución.
- Exponer el comando `adams-login` mediante el entry point del proyecto.
- Cargar `.env` únicamente al ejecutar el CLI; las variables de entorno ya
  existentes tienen precedencia.
- Reutilizar el flujo de login de la Issue #126 con un contexto de navegador
  efímero y sin persistencia de credenciales, cookies ni sesión.
- Emitir únicamente `success`, `failed` o `blocked`.
- Clasificar como `failed` los errores de configuración, navegador o login que
  no puedan confirmarse.
- Clasificar como `blocked` CAPTCHA, MFA o cualquier intervención requerida,
  deteniendo el flujo sin intentar eludir esos controles.
- Documentar prerrequisitos, configuración local, uso y límites operativos.
- Cubrir con tests la carga de configuración, precedencia, estados, cierre del
  contexto y ausencia de secretos en la salida.

## Fuera de alcance

- Recargas, reintentos, bucles, monitorización o polling.
- Lectura de cursos, tareas, progreso, evaluaciones u otro contenido.
- Notificaciones, comunicaciones o acciones posteriores al login.
- Persistencia de credenciales, cookies, tokens o sesiones.
- Logs, telemetría o almacenamiento de diagnósticos; se reservan para una Issue
  posterior.
- Bypass de CAPTCHA, MFA, controles anti-automatización o intervención humana.
- Credenciales reales, datos de estudiantes, `.env` o artefactos operativos.

## Decisiones técnicas

1. `python-dotenv` se invoca desde el módulo CLI, nunca durante la importación
   del paquete.
2. `override=False` conserva la precedencia de variables de entorno existentes.
3. El CLI captura errores de configuración y ejecución y los presenta como
   `failed`, sin imprimir la excepción ni sus valores.
4. El detector existente de CAPTCHA/MFA/intervención devuelve `blocked`; no se
   añade ningún mecanismo de evasión.
5. El proceso termina después de un intento y del cierre del contexto efímero.
   No se añadirá ningún mecanismo de recarga, reintento o monitorización.

## Archivos esperados

- `docs/plans/issue-128-implementation-plan.md` — este plan aprobado.
- `README.md` — instalación, uso y límites explícitos del CLI.
- `docs/installation-and-operation.md` — procedimiento operativo y límites.
- `pyproject.toml` y `uv.lock` — entry point y dependencia declarada.
- `src/adams_tutoria/adams_login_cli.py` — punto de entrada one-shot.
- `src/adams_tutoria/adams_login.py` — reutilización del flujo y clasificación
  de bloqueos, sin ampliar su alcance.
- `tests/unit/test_adams_login_cli.py` y
  `tests/unit/test_adams_login.py` — cobertura automatizada sintética.

## Estrategia de validación

La validación se separa explícitamente en tres capas para no confundir un
fallo preexistente de otra Issue con un defecto de #128:

### Validación específica de Issue #128

- Ejecutar los tests focalizados del login y del CLI.
- Verificar el entry point y el comportamiento sin `.env` con configuración
  sintética, sin conectar con ADAMS ni usar credenciales reales.
- Ejecutar `ruff check .`, `ruff format --check .`, `mypy src` y `uv lock --check`
  cuando sean aplicables.
- Revisar que `.env` sigue ignorado, que no se añaden logs y que la salida no
  contiene secretos.
- Comprobar cada criterio de aceptación de #128 de forma independiente.

### Regresión global

- Ejecutar la suite completa `uv run pytest` y conservar su resultado literal,
  incluyendo cualquier fallo.
- Ejecutar las comprobaciones globales de lint, formato y tipado cuando sean
  aplicables, registrando sus resultados sin reinterpretarlos.

### Baseline preexistente

- Para cada fallo de la suite global, registrar el test exacto, su causa y el
  comportamiento observado antes de atribuirlo a #128.
- Considerar un fallo parte del baseline únicamente si es reproducible fuera
  del alcance de #128, afecta a código/tests no modificados por #128 y no
  contradice ningún criterio de aceptación de #128.
- No corregir, ocultar ni reclasificar fallos de otra Issue dentro de #128.

## Regla de READY

El estado puede ser `READY FOR HUMAN REVIEW` aunque la regresión global tenga
resultado `FAIL` **solo si** se cumplen simultáneamente todas estas
condiciones: (1) todos los criterios de #128 y todas las validaciones
específicas pasan; (2) el resultado global se conserva literalmente; (3) cada
fallo global está identificado y atribuido con evidencia al baseline
preexistente; (4) el fallo afecta únicamente a código/tests fuera del alcance
de #128 y no fue introducido ni enmascarado por sus cambios; y (5) no existe
un riesgo de privacidad, seguridad o regresión propio de #128. Si alguna
condición no se puede demostrar, el estado debe ser `NOT READY`.

## Riesgos y supuestos

- El markup real de ADAMS puede cambiar; el prototipo solo reconoce los
  selectores definidos por la Issue #126.
- Un error inesperado se comunica deliberadamente como `failed`, sin detalles
  diagnósticos en stdout.
- La presencia de CAPTCHA/MFA/intervención bloquea el intento y nunca se
  interpreta como una invitación a automatizar o eludir el control.
- La ejecución real requiere que el usuario prepare localmente `.env` y el
  navegador de Playwright; esos artefactos no forman parte del repositorio.

## Dependencias

- Issue #126, ya mergeada, para el flujo de login seguro existente.
- Python 3.13, `uv`, Playwright y `python-dotenv`.

## Delegación

- Implementer: aplicar únicamente este alcance en la rama de la Issue.
- Validator: comprobar independientemente cada criterio, ejecutar los checks y
  producir/actualizar el informe durable de validación.
- Reviewer: revisar alcance, seguridad, privacidad, mantenibilidad y ausencia
  de reintentos, monitorización y logs.

Este plan está aprobado para la implementación de la Issue #128.
