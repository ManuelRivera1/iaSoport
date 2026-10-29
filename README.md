# Support AI

La barra superior incluye **Volver** e **Inicio del módulo**. También puedes usar
Atrás y Adelante del navegador para volver entre pantallas, carpetas y documentos.
En el chat, **Volver a las preguntas de inicio** recupera las tarjetas de sugerencias.

**Documentar conocimiento** sirve para explicar proyectos, servicios, APIs y procedimientos.
**Registrar un error** tiene su propio formulario para síntomas, causa, solución y verificación.
Puedes guardar un error en investigación y retomarlo desde **Mis borradores**.

La ayuda con notas es opcional y está plegada al inicio del formulario de conocimiento:
pega apuntes, pulsa **Completar campos con mis notas** y revisa los campos resaltados.
La IA completa solo campos vacíos; las notas originales permanecen en el borrador y
no se publican con el documento. También puedes llenar el formulario sin utilizar IA.

Las eliminaciones pasan por **Por eliminar**: el documento se conserva hasta indicar
un motivo, escribir **ELIMINAR** y confirmar. Incluye `deletions/` en el commit para
que la justificación acompañe la retirada del archivo en el PR.

El editor permite cambiar identificación y contenido por secciones, conservando los
ejemplos y diagramas. **Continuar** es la acción principal del formulario; **Guardar
borrador** solo guarda trabajo local. **Preparar cambios locales** guarda el borrador
automáticamente y prepara su incorporación, sin enviar nada a Git ni a un PR.

## Trabajo en equipo con Git

Todos pueden editar documentos y gestionar proyectos, servicios, áreas, equipos y
 tipos desde **Catálogos**, sin cuentas ni contraseñas locales.

Los documentos están en `knowledge/` y los catálogos en `catalogs.json`; incluye ambos
 en tus commits. Trabaja en `feature/...`, sube tu rama y abre un PR hacia `trunk`.
El líder aprueba en el PR. La incorporación dentro de la interfaz solo actualiza tu
 guía local; no equivale a aprobar ni integrar cambios al repositorio remoto.

Configura en el servicio Git la protección de `trunk` y los revisores obligatorios.
La aplicación no hace push ni integra ramas automáticamente.
Más detalles en [el flujo de colaboración](docs/administration.md).

## Guía local y portable: flujo recomendado

Cada persona descarga su copia, documenta y comparte los cambios desde la interfaz.
No requiere publicar la aplicación ni conectarse a una organización Git.

1. En un equipo nuevo, ejecuta **Instalar Support AI.cmd** una vez. Requiere Git,
   Internet para descargar dependencias y el modelo. El instalador busca Python
   3.12 o 3.13; si falta, intenta instalar Python 3.13 mediante WinGet para el
   usuario actual. Puedes conservar otras versiones de Python, incluida 3.15.
   Si WinGet no esta disponible, el instalador indica como instalar Python 3.13.
2. Ejecuta **Abrir Support AI.cmd**. En este equipo ya está instalado.
3. Usa **Documentar conocimiento** para organizar notas por proyecto, área y tipo,
   incluyendo endpoints, CORS, autenticación, configuración y errores.
4. En **Importar y compartir** puedes importar Markdown, TXT y JSON (OpenAPI/Postman).
5. Revisa y aprueba las propuestas en **Mi documentación → Por revisar**.
   Solo entonces alimentan las respuestas del chat.
6. Descarga **Mi guía** para enviar los documentos aprobados a otra persona;
   ella los importa y revisa en su copia. **Aplicación sin modelos** permite entregar
   también el código y el instalador, sin copiar los archivos pesados.

Puedes editar Markdown en `knowledge/`: los cambios se detectan cada 15 segundos
mientras la aplicación está abierta. Preguntar no añade hechos automáticamente.

La búsqueda predeterminada ahora es ligera, sin PyTorch, embeddings ni Qdrant.
Los modelos de IA siguen ocupando varios GB por equipo: se instalan aparte una vez
y se reutilizan. Los paquetes excluyen modelos, cachés, bases de datos y borradores.

Lee [la guía local y portable](docs/portable-guide.md). Para generar el ZIP:

```powershell
.\.venv\Scripts\python.exe scripts/build-portable.py
```

Resultado: `data/releases/SupportAI-portable.zip`.
Si tienes la versión anterior abierta, ciérrala con Ctrl+C y vuelve a abrirla.

## Referencia del modo anterior con repositorio explícito

Los pasos siguientes se conservan como referencia avanzada. Para el uso cotidiano
utiliza el flujo recomendado de arriba, que administra su historial local.

Plataforma privada de conocimiento técnico basado en Git. MVP local con interfaz web,
documentación guiada, índice incremental, búsqueda híbrida y chat local con Ollama.
El chat responde con citas textuales verificadas de los archivos Markdown.

## Uso sencillo

Haz doble clic en **Abrir Support AI.cmd**. La aplicación abre el navegador.
Si todavía está abierta la API anterior, ciérrala con Ctrl+C antes de iniciar.

- **Preguntar al conocimiento:** chat con fuentes, sin escribir JSON.
- **Documentar un microservicio:** notas, ayuda local para organizar campos,
  formulario guiado, revisión, descarga y borradores guardados.
- **Mi documentación:** consulta el conocimiento existente o retoma un borrador.

Consulta la [guía de la interfaz](docs/interface.md). Todo permanece en tu equipo.
Los borradores requieren revisión antes de incorporarse al conocimiento oficial.

## Abrir el chat

Ollama y el modelo ya se prepararon en este equipo. Detén la API anterior con Ctrl+C.
Desde la carpeta del proyecto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

En otra terminal:

```powershell
cd C:\book\iaSoport
.\.venv\Scripts\python.exe -m support_ai.console
```

Escribe tu pregunta. Para documentar microservicios por área y tema, utiliza
[la plantilla](templates/microservicio.md). Consulta [la guía del chat](docs/chat.md)
para actualizar los archivos y sus índices. La interfaz web ya incluye estas tareas.

## Ejecutar en Windows PowerShell

Requisitos: Git y Python 3.12 o 3.13. En este equipo se detectó Python 3.13.2.
Desde `C:\book\iaSoport`:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
New-Item -ItemType Directory -Force data/demo-knowledge
Copy-Item examples/knowledge/*.md data/demo-knowledge/
git -C data/demo-knowledge init -b main
git -C data/demo-knowledge add .
git -C data/demo-knowledge -c user.name=Demo -c user.email=demo@example.invalid -c core.hooksPath= commit -m 'Documentación ficticia inicial'
$env:SUPPORT_AI_REPO = "$PWD/data/demo-knowledge"
$env:SUPPORT_AI_REF = 'main'
.\.venv\Scripts\python.exe -m uvicorn support_ai.main:app --host 127.0.0.1 --port 8000
```

Si `py` apunta al alias de Microsoft Store, usar el ejecutable instalado:
`& 'C:\Users\Manuel\AppData\Local\Programs\Python\Python313\python.exe' -m venv .venv`.
No es necesario activar scripts de PowerShell ni cambiar ExecutionPolicy.

En otra terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/api/v1/knowledge/snapshot | ConvertTo-Json -Depth 5
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

La primera instalación necesita Internet. Este componente funciona después sin red;
la instalación completa offline del futuro RAG requerirá conservar ruedas, imágenes
y pesos. `requirements-lock.txt` registra las versiones verificadas de esta entrega.

## Criterios de aceptación de esta entrega

- Health responde 200 sin necesitar modelos ni base de datos.
- Snapshot devuelve exclusivamente Markdown confirmado de la referencia configurada.
- Cada documento incluye ruta, SHA-256 y commit reproducible.
- Cambios sin commit y archivos ajenos a Markdown no entran al snapshot.
- Una eliminación confirmada desaparece en la siguiente lectura.
- Repositorio inexistente responde 503 sin exponer stderr ni rutas del servidor.
- Referencias que intentan introducir opciones Git y documentos demasiado grandes se rechazan.
- Pytest y Ruff pasan.

No exponer esta API fuera de localhost: aún no tiene autenticación. La ruta del
repositorio se configura en el servidor, nunca se acepta desde una petición.
No se hacen clones, pulls, checkouts ni escrituras al repositorio o a producción.
La indexación escribe exclusivamente en la base local. El snapshot continúa siendo
una lectura directa de Git; el índice contiene la última sincronización exitosa.
La sincronización todavía es manual y no descarga cambios de un servidor remoto.
Se incluye detección básica de secretos en la ingesta; utiliza documentación ficticia.

Consulta [arquitectura](docs/architecture.md) y [dependencias](docs/dependencies.md).
La siguiente entrega se iniciará después de confirmar que este componente funciona.

## Verificación de la segunda entrega

En Windows/Python 3.13.2: catorce pruebas pasaron, Ruff pasó y `pip check` no
encontró incompatibilidades. Se verificaron altas, cambios, bajas, persistencia
tras reinicio, aislamiento por origen/rama y rollback si una ingesta falla.
Starlette emitió una advertencia de deprecación por usar HTTPX en TestClient;
no afecta estas pruebas, pero su migración queda pendiente.

Para reproducir las versiones verificadas en un entorno limpio:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

## Probar la segunda entrega

Si la API anterior sigue ejecutándose, detenla con Ctrl+C. No necesitas recrear el
repositorio ficticio ni el entorno virtual. Desde la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m uvicorn support_ai.main:app --host 127.0.0.1 --port 8000
```

En otra ventana de PowerShell:

```powershell
# Primera sincronización: indexa los documentos confirmados.
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/sync

# Consultar el estado persistido y los fragmentos con sus fuentes.
Invoke-RestMethod http://127.0.0.1:8000/api/v1/knowledge/status
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/knowledge/chunks?limit=50' | ConvertTo-Json -Depth 6

# Sin cambios en Git: chunks_created debe ser 0 y unchanged debe ser 3.
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/sync
```

En el ejemplo original la primera sincronización informa `added: 3`; si ya se
ejecutó, informa `unchanged: 3`. Detener y reiniciar la API conserva el índice.
La base se guarda en `data/support-ai.db`; puede configurarse antes del arranque
con `$env:SUPPORT_AI_DB = "$PWD/data/otro-indice.db"`.
Ejecuta un único proceso Uvicorn, sin `--workers` adicionales.

Consulta [detalles y aceptación de la segunda entrega](docs/ingestion.md).

## Probar la tercera entrega

Consulta la [guía de embeddings y búsqueda](docs/semantic-search.md) para instalar
las dependencias rag y descargar el modelo. Si ya están instalados, reinicia la API
y ejecuta en otra terminal:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/sync
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/vectorize

$body = @{ query = 'Que significa el error 504 en pagos'; top_k = 3 } | ConvertTo-Json
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/search -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) | ConvertTo-Json -Depth 8
```

Devuelve fragmentos originales con sus fuentes. Qdrant funciona en modo local
persistente en `data/qdrant`; Docker no necesita estar iniciado. Los pesos se guardan
en `data/models/multilingual-e5-small`. La primera consulta puede tardar al cargar el modelo.
Ejecuta solo un proceso sobre esa carpeta Qdrant. El chat local ya está disponible
según las instrucciones al inicio de este documento.

Verificación de la tercera entrega: 28 pruebas pasaron, Ruff pasó y `pip check`
no encontró incompatibilidades. La comprobación con E5 real recuperó primero la
fuente esperada en las tres consultas ficticias, con conexiones de red bloqueadas.
Se generaron cinco embeddings y la siguiente vectorización reutilizó los cinco.
