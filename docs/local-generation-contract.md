# Contrato de generación local

`GenerationRecord` vincula cada borrador a un `Enrollment` y a un
`communication_type`. Sus estados son `GENERATED`, `REVIEWED`, `EDITED`,
`COPIED`, `DISCARDED` y `SENT`. `SENT` únicamente registra manualmente que el
tutor realizó un envío externo después de copiar el texto: no llama a ADAMS,
SMTP, Ollama ni a ningún otro canal.

El payload futuro del modelo usa una allowlist (`communication_type`, `reason`
y contexto mínimo permitido). Nunca incluye nombre, correo, identificadores
externos, credenciales, sesiones, exports, informes crudos ni el registro
completo de la base de datos. La persistencia SQLite guarda el payload
minimizado y el borrador, en la base operativa local ignorada por Git. El
borrador puede borrarse explícitamente; no se implementa retención automática
ni envío automático.

## Puerto local y adaptador Ollama

La generación se solicita mediante el puerto sustituible `GenerationPort`, cuya
operación `generate(payload)` devuelve texto de borrador. `OllamaGenerator` es
el adaptador local incluido; recibe una `OllamaConfig` inmutable y un transporte
HTTP opcional inyectable para pruebas. El adaptador usa `POST /api/generate`,
envía `stream: false` y no cambia el estado de `GenerationRecord` ni realiza
envíos.

El endpoint por defecto es `http://localhost:11434`. Solo se aceptan endpoints
HTTP sin credenciales en `localhost`, `127.0.0.1` o `::1`; HTTPS, hosts remotos,
usuarios, contraseñas, consultas y fragmentos se rechazan. Timeout, tamaños
máximos de solicitud/respuesta y texto generado son límites explícitos. Las
respuestas deben ser JSON con un campo `response` de texto no vacío. Los
errores de configuración, transporte y respuesta usan excepciones tipadas.

## Persistencia y validación

`GenerationRepository.save` tiene semántica de *upsert* completo. Si ya existe
el mismo `id`, todos los campos persistidos (incluidos `enrollment_id`, payload,
texto, estado y marcas temporales) se sustituyen por los del valor recibido; no
se conserva silenciosamente una parte del registro anterior. `transition` solo
acepta las transiciones definidas por el contrato y no realiza ningún envío.

Los timestamps son conscientes de zona horaria y no pueden retroceder: cada
marca presente debe ser igual o posterior a `created_at`; además, cada
transición debe ser igual o posterior a la última marca existente. El orden de
las columnas (`reviewed_at` y `edited_at`) no impone un orden fijo: permite
`EDITED → REVIEWED` y volver a revisar después de editar. `draft_text` solo se
puede reemplazar en una transición a `EDITED`; `SENT` exige que exista
`copied_at`. Los valores de contexto de las pruebas son sintéticos
(`unit 1`, `progress summary`) y nunca identificadores personales.
