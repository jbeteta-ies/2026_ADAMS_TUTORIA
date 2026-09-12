# Búsqueda local de contenidos Markdown

`adams_tutoria.content_search.MarkdownIndex` ofrece un índice temporal en
memoria para una instancia de `Course`. Lee únicamente archivos `*.md` de la
ruta local configurada en `Course.content_source`; `LOCAL_PATH` y `REPOSITORY`
se interpretan como una carpeta local ya disponible. `REPOSITORY` no clona,
sincroniza ni accede a la red.

```python
from adams_tutoria.content_search import MarkdownIndex

index = MarkdownIndex()
index.index_course(course)
results = index.search(course, "criterio de evaluación")
```

Cada resultado incluye `module`, `document`, `path`, un `fragment` y una
puntuación determinista. La búsqueda no cruza cursos: cada curso debe
indexarse explícitamente. La normalización ignora mayúsculas, acentos y
espacios repetidos, y exige que todos los términos aparezcan en el documento.

No hay índice persistente, embeddings, UI, clonado, sincronización,
autenticación ni dependencias nuevas. Los contenidos operativos deben
permanecer fuera del repositorio; las pruebas usan Markdown sintético.

## Asistente de apoyo

`adams_tutoria.question_assistant.QuestionAssistant` reutiliza un
`MarkdownIndex` ya cargado para preparar un borrador determinista a partir de
una duda del tutor. El borrador solo incluye fragmentos que aparecen en el
curso recibido y cada fragmento conserva `module`, `document` y `path` como
referencia trazable. Si no hay coincidencias, lo indica explícitamente en vez
de inventar una respuesta.

El asistente no llama a ADAMS, no persiste el borrador y no envía mensajes. La
interfaz del dashboard solo lo muestra para revisión manual. El curso debe
indexarse explícitamente antes de usarlo; por tanto, varios cursos no se
mezclan accidentalmente.
