# Segunda entrega: índice incremental local

## Objetivo y archivos

Transformar documentos Git en fragmentos citables y conservarlos entre reinicios.
Implementación: `chunking.py`, `storage.py` e `ingestion.py`. Se amplía `main.py`
con tres endpoints y se añaden pruebas de integración en `test_ingestion.py`.

## Decisiones

- SQLAlchemy 2.0 con SQLite del Python instalado. Se evita instalar PostgreSQL para
  comprobar este componente monousuario. La arquitectura empresarial conserva
  PostgreSQL como destino; su conexión, migraciones y pruebas aún no se implementan.
- Tablas `repositories`, `documents` y `chunks`. El origen se identifica por ruta
  absoluta y rama configuradas, sin aceptar rutas del cliente HTTP.
- Fragmentos por encabezados y párrafos, con objetivo suave de 1400 caracteres.
  Conservan bloques de código cercados sin dividirlos, texto original y líneas
  inclusivas desde 1. Un párrafo o bloque de código grande puede superar el objetivo;
  el proveedor de embeddings deberá limitar tokens explícitamente en el próximo paso.
- ID determinista por ruta, hash de documento, ordinal y versión del fragmentador.
  Su clave en la base incluye el origen: no reutilizar solo este ID como clave global
  al agregar Qdrant o multiempresa.

La respuesta de fragmentos usa el commit del índice activo para todas las citas,
incluidos documentos reutilizados sin cambios. Es un commit donde el documento
existe con exactamente el contenido indexado; no pretende ser su último commit de edición.

## Sincronización

1. Leer un snapshot inmutable de la rama configurada.
2. Comparar rutas y SHA-256 con el manifiesto guardado.
3. Borrar documentos/fragmentos eliminados y reemplazar solo los modificados/nuevos.
4. Actualizar el commit activo y la fecha de éxito en la misma transacción SQL.
5. Si falla, hacer rollback y registrar un mensaje de error sin contenido sensible.

Los documentos sin cambios conservan sus IDs y no se vuelven a fragmentar.
Por ahora se leen todos los blobs Markdown para calcular el snapshot: incrementalidad
en persistencia y fragmentación, sin optimización todavía del tráfico de objetos Git.
Un cambio de versión del fragmentador fuerza regenerar los documentos existentes.
El cambio de configuración deberá acompañarse de un cambio de esa versión.

Un bloqueo en la aplicación serializa sincronizaciones y lecturas del índice. SQLite
usa transacciones explícitas (`autocommit=False`, Python >=3.12) para lecturas coherentes.
Esta entrega admite un proceso Uvicorn. No es un servicio distribuido ni ofrece
sincronización periódica, webhooks, fetch/pull o seguimiento histórico de ejecuciones.

## API

| Método/ruta | Resultado |
| --- | --- |
| POST /api/v1/knowledge/sync | Sincronización síncrona; commit, added, modified, deleted, unchanged, chunks_created |
| GET /api/v1/knowledge/status | Commit indexado, totales, fecha de éxito, último error |
| GET /api/v1/knowledge/chunks?offset=0&limit=50 | Total y fragmentos ordenados por ruta/ordinal; máximo 200 por página |

El estado inicial tiene commit nulo y cero documentos/fragmentos. Si la ingesta
falla, sync responde 503 y status permite consultar el último error y el commit
válido anterior. Una ingesta exitosa borra el error. `last_success_at` corresponde
a la última comprobación exitosa aunque no existan cambios. Health no crea la base.
Cambiar repo o rama utiliza otro espacio de nombres dentro de la misma base.
Esto no sustituye la autenticación ni el aislamiento empresarial.

## Seguridad y límites

La detección inicial rechaza claves privadas, patrones de claves AWS, tokens GitHub
y algunas asignaciones de contraseñas/tokens. Puede tener falsos positivos y negativos;
no certifica que un repositorio esté libre de secretos. No incluye historial Git.
El mensaje HTTP no muestra el secreto ni el contenido que lo activó. Solo la ingesta
usa esta comprobación: snapshot continúa exponiendo Markdown directamente en localhost.
La base contiene texto sin cifrar y debe protegerse con permisos del sistema operativo.

No se ejecutan comandos de documentos. No hay generación de respuestas ni interpretación
de instrucciones recuperadas. Mantener escucha en 127.0.0.1 y usar datos ficticios.
La documentación de origen debe usar UTF-8 y cumplir los límites previos de 500 archivos
y 512 KB por archivo. El índice conserva el estado actual, no un historial completo.

## Aceptación comprobable

1. Primera sincronización del ejemplo: tres documentos indexados y fuentes con líneas.
2. Segunda sincronización: cero fragmentos creados y tres documentos sin cambios.
3. Modificación confirmada: reemplazar fragmentos viejos del documento afectado.
4. Alta y baja confirmadas: agregar y retirar sus fragmentos, sin tocar otros documentos.
5. Reinicio de la API: conservar commit y contenido del índice.
6. Fallo tras escrituras parciales por posible secreto: rollback completo, contenido
   anterior accesible y último error visible; una corrección confirmada permite recuperarse.
7. Fragmentos reproducibles con CRLF/LF y bloques de comandos intactos.
8. Diferentes orígenes/ramas no mezclan documentos y los cambios sin commit se ignoran.

Siguiente componente, después de confirmación: embeddings locales y Qdrant.
