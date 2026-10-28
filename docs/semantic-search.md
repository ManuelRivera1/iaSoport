# Tercera entrega: embeddings y búsqueda semántica local

## Arquitectura

```text
Git -> sync -> fragmentos SQL -> vectorize -> Sentence Transformers CPU
                                                -> Qdrant local persistente
Consulta -> query: embedding -> Qdrant -> fragmentos con ruta, líneas y commit
```

Archivos nuevos: `embeddings.py`, `retrieval.py`, `tests/test_retrieval.py` y
`scripts/verify_semantic.py`. Se amplían esquema SQL y rutas FastAPI.

Docker Desktop está instalado, pero no se encontró un motor Docker en ejecución.
Se utiliza el modo local del cliente Qdrant, sin servidor ni API externa.
Es una opción para colecciones pequeñas y un proceso; no representa una validación
del servidor Qdrant, sus índices de producción, concurrencia o rendimiento a escala.
La migración al servidor Docker se hará en una entrega posterior.

## Instalación en Windows

Las dependencias base siguen en `requirements-lock.txt`; las dependencias completas
de esta entrega se registran en `requirements-rag-lock.txt`. Desde la carpeta del proyecto:

```powershell
# Instalación reproducible (incluye índice oficial de PyTorch CPU).
.\.venv\Scripts\python.exe -m pip install -r requirements-rag-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .

# Único paso que descarga los pesos del modelo.
.\.venv\Scripts\python.exe -m support_ai.embeddings
```

Alternativa para resolver dependencias de desarrollo desde los rangos de pyproject:

```powershell
.\.venv\Scripts\python.exe -m pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e '.[dev,rag]'
```

La descarga usa Hugging Face, obtiene una revisión concreta de
`intfloat/multilingual-e5-small` y escribe un manifiesto con commit y hashes SHA-256.
Descarga únicamente configuraciones, tokenizer y pesos safetensors, sin código Python
del repositorio del modelo. No es una API de inferencia comercial.
Repetir la descarga conserva la revisión del manifiesto existente; para cambiarla,
indicar `--revision` explícitamente. El primer uso resuelve la revisión oficial actual.
Para reinstalar offline se necesitan las ruedas compatibles con Windows/Python y una
copia completa de la carpeta del modelo; los archivos de versiones no incluyen esos binarios.

El modelo se carga desde disco, verifica hashes y usa `local_files_only=True`,
`trust_remote_code=False` y modo offline en las bibliotecas de Hugging Face.
La firma de caché incluye archivos/revisión, prefijos, normalización y versiones
de PyTorch, Sentence Transformers y Transformers. Cambiar modelo o bibliotecas obliga
a reconstruir embeddings; no se mezclan vectores de firmas distintas.

## Uso

Detén la API anterior con Ctrl+C y arranca una sola instancia:

```powershell
.\.venv\Scripts\python.exe -m uvicorn support_ai.main:app --host 127.0.0.1 --port 8000
```

En otra terminal:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/sync
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/vectorize
Invoke-RestMethod http://127.0.0.1:8000/api/v1/knowledge/vectors/status

$body = @{ query = 'Que significa el error 504 en pagos'; top_k = 3 } | ConvertTo-Json
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/search -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) | ConvertTo-Json -Depth 8
```

La búsqueda devuelve `hits`, cada uno con `score` y `source`: texto original,
ruta, commit, líneas e ID. `score` es similitud coseno, no probabilidad de certeza.
La búsqueda todavía no genera respuestas ni garantiza abstención para temas ausentes;
se presentan fragmentos candidatos. La recuperación híbrida y chat se implementarán después.

| Variable del servidor | Valor predeterminado |
| --- | --- |
| SUPPORT_AI_EMBEDDING_MODEL | data/models/multilingual-e5-small |
| SUPPORT_AI_QDRANT_PATH | data/qdrant |
| SUPPORT_AI_DB | data/support-ai.db |

Para otra carpeta del modelo, usa `python -m support_ai.embeddings --path RUTA` y
configura `SUPPORT_AI_EMBEDDING_MODEL` con esa misma ruta antes de arrancar la API.
Nunca aceptar rutas o modelos enviados por usuarios del endpoint.

## Consistencia e incrementalidad

`sync` conserva su función anterior: publica únicamente documentos/fragmentos SQL.
`vectorize` prepara la búsqueda a partir de ese estado:

1. Bloquear lecturas/sincronizaciones del proceso y fijar el commit de fragmentos.
2. Reutilizar embeddings por origen, firma de modelo e ID de fragmento.
3. Generar solo los faltantes, en lotes pequeños de CPU.
4. Escribir una colección nueva e inmutable en Qdrant, con todos los fragmentos vigentes.
5. Publicar su nombre, commit y caché mediante una transacción SQL.
6. Retirar la colección anterior después de publicar; eliminar su caché obsoleta.

La publicación es atómica para este proceso: un fallo antes del paso 5 conserva
la búsqueda anterior. No hay una transacción distribuida entre SQLite y Qdrant.
Una caída abrupta puede dejar una colección sin referencia; la limpieza administrativa
de esas colecciones queda pendiente. No borrar manualmente colecciones activas.
Si falla la limpieza de la colección anterior, puede quedar texto anterior en disco.
No es todavía una garantía empresarial de borrado físico o retención.

Repetir `vectorize` sin cambios no recalcula embeddings. Con un nuevo commit se
recrea la colección completa reutilizando vectores; las escrituras vectoriales aún
no son incrementales. Las citas de la colección usan siempre su commit de generación.
El caché SQL contiene vectores, no una copia adicional del texto de fragmentos antiguos.

`stale` compara commit SQL con el commit de vectores. Si hay cambios pendientes de
vectorizar, la búsqueda sigue usando la generación anterior y lo indica. Ese campo
no comprueba disponibilidad del disco, un nuevo HEAD sin sync ni cambios del modelo.
Si el modelo configurado cambió, search se rechaza hasta ejecutar vectorize.
Si no existen modelo o dependencias, los endpoints afectados devuelven 503;
health y la indexación de documentos siguen siendo independientes.

## Límites de entrada y seguridad

E5 usa prefijos `query:` y `passage:`, vectores normalizados y hasta 512 tokens.
Se comprueba el tamaño antes de codificar: no se trunca texto silenciosamente.
Un bloque grande conservado por el fragmentador puede exceder este límite;
en tal caso se rechaza la generación y se conserva la anterior. Reducir/seccionar
la documentación; no se sintetizan comandos para hacerlos encajar.

Las colecciones se separan por origen y cada búsqueda además filtra su identificador.
Esto no sustituye autenticación ni permisos multiempresa. Mantener localhost y datos
ficticios. Los modelos se configuran exclusivamente por el operador local.
El endpoint de búsqueda no ejecuta contenido de documentos ni llama a un LLM.
Qdrant local admite solo un proceso por carpeta: no arrancar verificaciones mientras
otra API esté usando esa carpeta, y no utilizar múltiples workers Uvicorn.

## Pruebas y aceptación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check

# Con la API detenida y modelo descargado: Qdrant y embeddings reales.
.\.venv\Scripts\python.exe scripts/verify_semantic.py
```

Las pruebas automatizadas usan Qdrant local real y un proveedor determinista
exclusivamente de prueba para verificar caché, bajas, cambio de modelo, reinicio,
rollback, filtrado de origen y contratos HTTP. Se omiten las pruebas vectoriales
si no se instaló el extra rag; el script real no utiliza ese proveedor de prueba.

Aceptación del script real: recuperar el documento correcto entre los tres primeros
resultados para órdenes, error 504 y conciliación SFTP; conservar citas del commit;
repetir vectorización con cero embeddings nuevos y funcionar bloqueando conexiones
de red del proceso. Es una evaluación pequeña, sin extrapolar calidad a datos reales.

Siguiente entrega, después de confirmación: recuperación híbrida y chat con Ollama,
incluyendo fuentes y abstención evaluada.

## Resultado verificado en este equipo

- Windows, Python 3.13.2; PyTorch 2.14.1+cpu, Sentence Transformers 5.7.0,
  Transformers 4.57.6 y Qdrant Client 1.20.0.
- Modelo: revisión `614241f622f53c4eeff9890bdc4f31cfecc418b3`, registrada
  junto a los hashes de archivos en el manifiesto local del modelo.
- Pytest: 28 pruebas pasaron. Ruff pasó y pip no detectó dependencias incompatibles.
- Verificación offline con E5 real: cinco fragmentos vectorizados, cero embeddings
  nuevos al repetir y la fuente esperada en primer lugar para las tres consultas.
- La prueba de consulta demasiado larga se rechazó sin truncamiento; el tokenizer
  emitió una advertencia de tamaño esperada, y no se ejecutó el modelo con ese texto.
- Persiste la advertencia de deprecación HTTPX/Starlette del cliente de pruebas.
