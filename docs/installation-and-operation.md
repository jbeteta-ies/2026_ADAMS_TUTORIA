# Instalación y operación

Esta guía describe el uso local del MVP de ADAMS Tutoria. La aplicación es una
herramienta de apoyo para el tutor: ADAMS sigue siendo la fuente de verdad para
la actividad del curso y el envío de comunicaciones.

> **Privacidad.** Los ejemplos de esta guía son sintéticos. No copies aquí
> nombres, correos, identificadores, exports, capturas de pantalla, mensajes ni
> credenciales reales. Los datos operativos deben permanecer en rutas locales
> ignoradas por Git.

## 1. Requisitos

- Python 3.13.
- [`uv`](https://docs.astral.sh/uv/) instalado y disponible en el `PATH`.
- Acceso local al repositorio.

No se necesita una cuenta de ADAMS para arrancar el banner CLI ni para explorar
el dashboard sintético. La aplicación no implementa autenticación, conexión de
envío a ADAMS ni sincronización automática.

## 2. Instalación con `uv`

Desde la raíz del repositorio:

```bash
uv sync
```

`uv sync` crea o actualiza el entorno virtual local `.venv/` y sincroniza las
dependencias declaradas en `pyproject.toml` y `uv.lock`. No es necesario
activar el entorno para usar los comandos de esta guía: se ejecutan con
`uv run`.

Para comprobar que el intérprete seleccionado es el esperado:

```bash
uv run python --version
```

Debe mostrar Python 3.13 o una versión compatible con `requires-python`.

## 3. Arranque

### 3.1 CLI

El punto de entrada preferido es:

```bash
uv run adams-tutoria
```

También está disponible la forma equivalente:

```bash
uv run python -m adams_tutoria
```

El CLI actual imprime el banner de versión y termina correctamente. No inicia
un servidor, no carga datos y no importa reportes. Es, por tanto, una
comprobación de instalación y un punto de entrada mínimo del MVP, no un modo
interactivo.

### 3.2 Dashboard Streamlit

Arranca el dashboard desde la raíz del repositorio:

```bash
uv run streamlit run src/adams_tutoria/dashboard.py
```

Streamlit mostrará una URL local en el terminal, normalmente
`http://localhost:8501`. Abre esa URL en el navegador. Para detenerlo, vuelve
al terminal y pulsa `Ctrl+C`.

El dashboard se ejecuta en el proceso local. No lo expongas a Internet ni
compartas su URL cuando la instancia esté trabajando con datos personales.

## 4. Uso del dashboard

La barra lateral contiene:

- **Navegación**: las secciones `Inicio`, `Curso` y `Edición`.
- **Curso**: selector de curso.
- **Edición**: selector dependiente del curso seleccionado.

La selección se conserva durante la sesión de Streamlit con `course_id` y
`edition_id`.

### Inicio

Muestra el shell del dashboard y el asistente de apoyo para dudas. El asistente
busca únicamente en el contenido Markdown sintético incluido para el curso de
demostración seleccionado. Al preparar un borrador se muestran sus referencias
para que el tutor lo revise; no se envía automáticamente.

### Curso

Presenta la información básica del curso seleccionado y un placeholder para
indicadores futuros.

### Edición

La edición de demostración muestra métricas sintéticas de matrículas:

- total;
- no iniciadas;
- inactivas;
- evaluaciones pendientes;
- finalizadas; y
- casos que requieren atención.

También permite filtrar y ordenar la tabla de seguimiento. Los identificadores,
estados, porcentajes y fechas que aparecen en esta vista pertenecen al proveedor
de demostración y no representan datos de ADAMS. Una misma matrícula puede
contribuir a varias métricas de motivos.

Al abrir una ficha sintética se pueden visualizar el perfil, el progreso, las
evaluaciones y el historial. Las acciones del tutor se guardan en la base
SQLite local configurada por defecto; no se escriben en ADAMS.

## 5. Importación genérica de reportes

El MVP incluye un lector estructural genérico, no un importador de un formato
ADAMS confirmado. La API `adams_tutoria.tabular_import.read_tabular` acepta
archivos locales `.csv` y `.xlsx` y devuelve filas asociadas a sus cabeceras.

Características verificadas:

- CSV en `utf-8-sig` y separado por comas por defecto; se pueden proporcionar
  otro carácter separador y codificación mediante `TabularImportConfig`.
- XLSX leído con `openpyxl` en modo de solo lectura y usando valores, no
  fórmulas.
- Validación de cabeceras vacías o duplicadas, anchura de fila y columnas
  requeridas.
- Rechazo de valores vacíos en las columnas configuradas como obligatorias.
- Resultado parcial con filas aceptadas y diagnósticos seguros para filas
  rechazadas.

Ejemplo sintético de uso desde Python (no es un formato ADAMS):

```python
from adams_tutoria.tabular_import import TabularImportConfig, read_tabular

result = read_tabular(
    "data/private/ejemplo-sintetico.csv",
    config=TabularImportConfig(
        required_columns=("course_reference", "edition_reference"),
        required_non_empty_columns=("edition_reference",),
    ),
)
print(len(result.accepted), len(result.rejected))
```

El lector **no** hace ninguna de estas operaciones:

- no reconoce columnas concretas de ADAMS ni afirma que exista un formato
  estable;
- no convierte automáticamente las filas en alumnos, matrículas, progreso o
  evaluaciones;
- no reconcilia duplicados ni empareja identidades;
- no persiste filas en SQLite ni copia el archivo fuente; y
- no ofrece todavía un botón de importación en el dashboard.

La operación local de importación se puede abrir con:

```bash
uv run streamlit run src/adams_tutoria/import_ui.py
```

La pantalla acepta únicamente `.xlsx`, ofrece los tres tipos iniciales
(alumnos/matrículas, progreso y evaluaciones), muestra el historial de metadatos
seguros y separa la presentación de `ImportOperationService`. La UI no define
un formato ADAMS: una integración debe adaptar las filas mediante los contratos
existentes antes de producir el `PreparedImport`. La confirmación es siempre
total y explícita; cualquier `REJECTED`, `CONFLICT` o `ERROR` la bloquea.
No se guardan el fichero fuente ni sus filas.

La operación confirmada se ejecuta en una única transacción SQLite: si falla
cualquier parte del lote, se revierten las altas o cambios parciales y se
conserva solo un registro global de error, sin filas brutas. Repetir la misma
clave de idempotencia no duplica el lote ni sus entidades. Los cambios de
progreso y evaluaciones se mantienen como histórico; una reimportación sin
cambios se registra como `UNCHANGED`.

Por tanto, el flujo operativo seguro para un reporte real es conservar la
fuente localmente bajo `data/private/`, confirmar primero su procedencia y
estructura, y no presentarla como compatible hasta disponer de una adaptación
específica y aprobada. No inventes nombres de columnas, escalas, reglas de
aprobación o correspondencias de identificadores.

### Flujo `evolution_xlsx` (interfaz operativa de #112)

La vía API local reproducible es **la interfaz operativa aprobada de #112**:
`import_evolution_xlsx(path, database_path, edition_id, imported_at,
confirm=False)`. Con `confirm=False` produce el preview sin escrituras; con
`confirm=True` aplica el mismo plan únicamente tras la confirmación humana
explícita. Esta API es la interfaz operativa reproducible y verificable del
flujo. Una UI o una CLI adicional quedan expresamente fuera de alcance en
#112; no son interfaces alternativas implícitas ni requisitos pendientes.

El importador específico de evolución usa el XLSX operativo únicamente desde
una ubicación local ignorada, normalmente `data/private/`. No copies el archivo
ni sus filas al repositorio. El flujo es:

1. Ejecuta la operación en modo **preview** y revisa los contadores de cambios,
   sin cambios, rechazos y `excluded`. Las exclusiones explícitas (por ejemplo,
   presentación, actividades, evaluaciones, resumen o caso final) se muestran
   como diagnóstico informativo y no son errores ni bloquean la confirmación.
2. Verifica los diagnósticos de identidad y porcentajes. Solo se resuelven
   matrículas existentes mediante el identificador estable aprobado; nunca por
   nombre o posición.
3. Confirma explícitamente la aplicación. La escritura es transaccional y
   actualiza el estado actual, no un histórico de snapshots.
4. El lote calcula un fingerprint SHA-256 del archivo y una clave de
   idempotencia por edición. Repetir el mismo archivo no duplica cambios ni
   nodos.

Los porcentajes de páginas y el porcentaje global de la columna G (`Evolución`)
se almacenan por separado. Si un módulo o submódulo falta en una importación
posterior, se conserva el último estado conocido: la ausencia no significa cero,
borrado, reinicio ni retroceso. Cuando un lote contiene un módulo y sus
submódulos, preview y apply usan el mismo orden lógico de dos pasadas: primero
se planifican/aplican los módulos y después los submódulos, sin crear padres
implícitos fuera del lote.

## 6. Comunicaciones manuales

El flujo de comunicaciones del dashboard requiere revisión humana y no llama
a ADAMS:

1. Revisa la sugerencia mostrada para la matrícula.
2. Pulsa **Aprobar mensaje para revisión**.
3. Lee el texto completo renderizado y edítalo fuera de la aplicación si hace
   falta.
4. Selecciona o descarga el texto y cópialo manualmente en ADAMS.
5. Después de copiarlo, pulsa **Registrar COPIED**.
6. Tras comprobar que el envío se realizó manualmente en ADAMS, pulsa
   **Registrar SENT**.

El historial guarda estados, referencias y marcas temporales; el texto
renderizado no se persiste en el registro. `SENT` significa que el tutor ha
confirmado la acción manual en ADAMS, no que la aplicación la haya ejecutado.
No introduzcas credenciales, cookies ni tokens en la aplicación o en la
documentación.

## 7. Datos locales y configuración

Por defecto, las rutas se calculan respecto al directorio de trabajo:

| Ruta | Uso |
| --- | --- |
| `data/private/` | Exports, fuentes de importación y comunicaciones privadas |
| `data/local/` | Estado local y base SQLite operativa |
| `data/local/adams_tutoria.sqlite3` | Base inicializada explícitamente por la persistencia |

`data/`, las bases SQLite, sus sidecars, `.env` y backups habituales están
ignorados por Git. Esta protección no sustituye comprobar los permisos del
sistema operativo ni la ruta efectiva.

La configuración de rutas puede ajustarse mediante estas variables, evaluadas
cuando se llama a `load_config()`:

- `ADAMS_TUTORIA_BASE_DIR`
- `ADAMS_TUTORIA_DATA_ROOT`
- `ADAMS_TUTORIA_PRIVATE_DATA_DIR`
- `ADAMS_TUTORIA_LOCAL_DATA_DIR`

Las rutas relativas se interpretan respecto a la base configurada. Si eliges
una ruta fuera de `data/`, verifica expresamente que no pueda entrar en Git y
que tenga permisos adecuados. No se usa un cargador de `.env`.

La inicialización de SQLite es explícita e idempotente. El paquete no abre la
base al importarse. El diseño actual no utiliza cifrado en reposo, control de
acceso propio, WAL ni migraciones versionadas; protege los datos mediante el
entorno local y los permisos del sistema.

Estos límites son deliberados: no hay backup automático, retención automática,
autenticación, conectores remotos, scraping ni envío a ADAMS. Una ruta
configurada fuera de `data/` debe comprobarse manualmente antes de operar.

## 8. Copias de seguridad y retención

No hay un mecanismo de backup automático. El operador debe establecer una
rutina manual acorde con la política de su entorno:

1. Detén el dashboard antes de copiar la base, para evitar una copia
   inconsistente durante una escritura.
2. Copia `data/local/adams_tutoria.sqlite3` a un medio local o institucional
   protegido, fuera del repositorio.
3. Conserva también los archivos privados que sean necesarios para reconstruir
   el trabajo, sin duplicar exports innecesariamente.
4. Comprueba la ubicación y permisos de la copia; no la subas a GitHub.
5. Elimina manualmente copias, exports, comunicaciones y sidecars cuando ya no
   sean necesarios, de acuerdo con las reglas de tu organización.

Los backups contienen potencialmente datos personales. No se incluyen backups,
exports ni bases de ejemplo en este repositorio. Antes de restaurar, detén la
aplicación, conserva la base actual por si fuera necesario volver atrás y
verifica que el archivo restaurado procede de una copia confiable.

## 9. Incorporar nuevos cursos

El modelo de dominio es genérico: un `Course` puede tener varias `Edition` y
puede referenciar un `ContentSource` local o un checkout de repositorio. La
referencia de contenido se almacena como metadato; la aplicación no clona ni
sincroniza repositorios.

En el estado actual, el dashboard de demostración utiliza un catálogo sintético
definido en código (`COURSES` y `EDITIONS`) y contenido Markdown de ejemplo.
No existe todavía una pantalla operativa para registrar cursos o ediciones ni
un procedimiento soportado para conectarlos a reportes reales. Añadir un curso
real requiere una Issue que defina la fuente, el contrato de importación y la
persistencia; no debe resolverse editando manualmente la documentación ni
inventando un formato ADAMS.

Para preparar contenido seguro para una futura integración, mantenlo en su
repositorio correspondiente, sin mezclarlo con `data/private/` ni con datos de
alumnos. Usa identificadores y ejemplos sintéticos hasta que exista un flujo
aprobado.

## 10. Troubleshooting

### `uv: command not found`

Instala `uv` siguiendo su documentación oficial y abre un terminal nuevo para
que el `PATH` se actualice. No instales dependencias del proyecto globalmente.

### `uv sync` falla o selecciona otro Python

Comprueba `uv python list` y `uv run python --version`. Instala Python 3.13 y
vuelve a ejecutar `uv sync`. Revisa que estás en la raíz que contiene
`pyproject.toml` y `uv.lock`.

### El CLI no abre una ventana

Es el comportamiento esperado: `uv run adams-tutoria` solo imprime el banner y
termina. Usa el comando de Streamlit para abrir la interfaz.

### Streamlit no encuentra `adams_tutoria`

Ejecuta el comando desde la raíz del repositorio y usa exactamente:

```bash
uv run streamlit run src/adams_tutoria/dashboard.py
```

Si el puerto predeterminado está ocupado, Streamlit puede ofrecer otro puerto;
abre la URL que indique el terminal.

### La pantalla muestra datos sintéticos

Es intencional en el MVP. El dashboard no lee automáticamente exports ni
convierte un reporte ADAMS en datos de operación. Verifica que no estás usando
la demo como evidencia de actividad real.

### Un importador rechaza un archivo

Confirma que la extensión es `.csv` o `.xlsx`, que la cabecera no tiene nombres
vacíos o duplicados, que todas las filas tienen la misma anchura y que las
columnas requeridas contienen valores. Los números de fila de los diagnósticos
son ordinales de registros de datos, no necesariamente números de línea física
de un CSV con campos multilínea.

### No aparece una comunicación

La sugerencia debe existir para la matrícula sintética y debe aprobarse antes
de mostrar el texto completo. La aplicación no consulta ADAMS ni genera
sugerencias a partir de un export real en este alcance.

### Se necesita recuperar una base

Detén Streamlit, no sobrescribas la copia actual sin conservarla y restaura una
copia local confiable en la ruta configurada. Revisa permisos y evita dejar la
copia o sus sidecars en una ruta versionada.

## 11. Limitaciones conocidas

- El CLI no ofrece todavía una interfaz interactiva.
- El dashboard usa un proveedor y catálogo sintéticos para la mayor parte de
  la experiencia.
- No hay importación ADAMS específica, reconciliación, sincronización ni
  persistencia automática de reportes.
- No hay autenticación, cifrado, backup automático ni retención automática.
- Las comunicaciones siempre requieren copiar y enviar manualmente en ADAMS.
- El catálogo de nuevos cursos y ediciones no es aún una operación de usuario;
  requiere una futura ampliación aprobada.

Estas limitaciones son deliberadas para este MVP. No deben ocultarse mediante
ejemplos que parezcan datos reales ni mediante afirmaciones sobre formatos de
ADAMS que todavía no han sido verificados.

## 12. Generación local con Ollama (preparación manual)

La generación asistida es opcional y local. Los tests del proyecto no necesitan
Ollama, no lo arrancan y no descargan modelos. Para una operación manual, el
operador debe instalar Ollama siguiendo la documentación oficial de su sistema,
iniciarlo como servicio local y preparar previamente un modelo aprobado por su
organización. La aplicación no instala Ollama, no ejecuta `ollama pull`, no
elige modelos por su cuenta y no acepta endpoints remotos.

Antes de operar:

1. Instala Ollama fuera del repositorio y verifica manualmente que el servicio
   escucha solo en el equipo local.
2. Descarga/prepara manualmente el modelo autorizado, conforme a la política
   del entorno; no guardes el modelo dentro del repositorio.
3. Configura el nombre del modelo y, si aplica, el endpoint local mediante la
   configuración de la aplicación. El valor predeterminado es
   `http://localhost:11434`.
4. Comprueba que el endpoint no contiene credenciales, consultas ni fragmentos.
   Solo se permiten `localhost`, `127.0.0.1` o `::1` por HTTP.
5. Arranca la aplicación local y selecciona explícitamente las matrículas que
   quieres revisar. La selección no decide destinatarios ni mezcla contextos.

El adaptador usa el puerto local `/api/generate` con `stream: false`, límites de
tiempo/tamaño y errores tipados. Cada matrícula produce como máximo un borrador
por solicitud. Un fallo de Ollama afecta solo a esa matrícula; se registra un
código de error mínimo y las demás pueden continuar. No hay fallback que envíe,
apruebe o marque un borrador automáticamente.

El tutor debe revisar cada motivo, contexto minimizado y texto. Puede editar,
regenerar, descartar o copiar individualmente. `COPIED` registra la copia
manual y `SENT` solo puede registrarse después de que el tutor haya realizado
manualmente la acción externa; la aplicación no tiene ruta de envío a ADAMS,
SMTP ni a otro servicio. La revisión humana y el copiado manual no se pueden
sustituir por el modelo.

Los datos reales solo deben cargarse desde rutas locales ignoradas, como
`data/private/` para fuentes y `data/local/` para la base y textos operativos,
o desde una ubicación externa protegida comprobada manualmente. No copies
exports, mensajes, logs, capturas, credenciales, cookies, tokens, modelos ni
bases reales al repositorio. Los tests y ejemplos usan únicamente datos
sintéticos y `tmp_path`; la protección de Git no sustituye los permisos del
sistema ni una revisión de la ruta efectiva.
