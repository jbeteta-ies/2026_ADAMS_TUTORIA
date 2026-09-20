# Catálogo operativo de cursos y ediciones

Issue #114 mantiene un catálogo local, no una copia ni una fuente de verdad de
ADAMS. Cursos y ediciones tienen UUID locales estables; sus referencias externas
son metadatos minimizados y no contienen credenciales, sesiones ni exportaciones.

## Ciclo de vida y selección

Los registros nacen `active`. Archivar/desactivar cambia únicamente el estado
operativo y conserva UUID, relaciones e histórico; reactivar lo restaura. Las
consultas `active_only=True` excluyen registros archivados y las listas ordenan
por nombre/etiqueta y UUID para que la selección sea determinista.

## Idempotencia y actualización

Crear de nuevo un curso con el mismo código, o una edición con la misma pareja
curso--referencia externa (o etiqueta cuando no hay referencia), devuelve el
registro existente. Las actualizaciones permitidas modifican metadatos sin
cambiar UUID ni relaciones. No hay borrado físico.

La inicialización es aditiva. No se eliminan ni remodelan columnas existentes.
La migración de una base heredada de catálogo detecta duplicados y se detiene con
un error explícito; el servicio también rechaza identidades ambiguas al crear.
No se escoge, reasigna ni elimina una fila automáticamente.

## Limitaciones y separación de ADAMS

El catálogo no importa XLSX, sincroniza, conecta con ADAMS, envía comunicaciones
ni invoca SMTP, Ollama u otros servicios. Los datos operativos permanecen en la
SQLite local ignorada por Git. Resolver duplicados históricos requiere una
decisión explícita antes de continuar.
