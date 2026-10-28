# Chat local y documentación sencilla

## Uso diario

El conocimiento sigue estando en archivos Markdown locales, versionados con Git.
La IA busca en esos documentos y selecciona citas para contestar. No tienes que
introducir documentos a mano en SQLite o Qdrant: son índices derivados.

1. Detén la API anterior con Ctrl+C.
2. Desde la carpeta del proyecto, arranca:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

3. En otra terminal, abre el chat:

```powershell
cd C:\book\iaSoport
.\.venv\Scripts\python.exe -m support_ai.console
```

Pregunta `¿Qué significa el error 504 en ms-payment?` o
`¿Cuál es el cURL para consultar una orden?`. Usa `/salir` para cerrar el cliente.
La primera pregunta puede tardar mientras se cargan modelos. El chat no guarda
historial y cada pregunta es independiente. No requiere navegador.

El arranque no descarga nada. Si necesitas reinstalar Ollama y sus pesos:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare-ollama.ps1
```

La preparación descarga el paquete portable oficial, conserva release/checksum en
`data/ollama/installation.json` y el digest del modelo en `data/ollama/model.json`.
Es una instalación local, sin registrar servicios ni alterar el PATH. El modelo
se guarda en `data/ollama-models`. Un proceso Ollama queda ejecutándose en segundo
plano en `127.0.0.1:11434`, con cloud deshabilitado para el servidor iniciado aquí.
Si ya existe un servidor Ollama, se reutiliza y el operador debe comprobar su configuración.
Cerrar FastAPI no detiene Ollama; puede gestionarse desde el Administrador de tareas
identificando el ejecutable de `data/ollama`, sin detener otras instalaciones.

## Dónde escribir el conocimiento

Plantilla: [microservicio.md](../templates/microservicio.md). Organización sugerida
dentro del repositorio configurado (actualmente `data/demo-knowledge`):

```text
pagos/
  ms-payment/
    servicio.md
    errores.md
facturacion/
  ms-invoice/
    servicio.md
```

También puedes usar un único `servicio.md` por microservicio. La plantilla contiene
área, tema, responsabilidad, dependencias, diagrama Mermaid, API, errores y procedimientos.
Sustituye los marcadores con información revisada antes de indexarla.
El diagrama permanece como texto Mermaid; el chat por terminal no lo dibuja.

Para publicar cambios que ya revisaste en el repositorio de ejemplo:

```powershell
git -C data/demo-knowledge add .
git -C data/demo-knowledge -c user.name=Demo -c user.email=demo@example.invalid -c core.hooksPath= commit -m 'Actualizar documentacion revisada'
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/sync
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/knowledge/vectorize
```

Estos comandos son para el repositorio ficticio local. Los repositorios reales
necesitarán su flujo de revisión y ramas autorizadas; no conectar datos sensibles
antes de incorporar autenticación y reforzar la detección de secretos.

## API y decisiones

`POST /api/v1/chat`, cuerpo `{"question":"Que significa el error 504"}`.
Devuelve answer, abstained, indexed_commit y sources con ruta, commit, líneas y cita.
Errores del runtime o un índice pendiente de vectorizar devuelven 503.
Las preguntas vacías o mayores de 2000 caracteres se rechazan con 422.

Se combina similitud semántica con BM25 sobre términos y rutas; los rankings se
fusionan con Reciprocal Rank Fusion. Ambos usan la misma generación de Qdrant.
El BM25 se calcula en memoria para este corpus pequeño, sin instalar otra base.
La búsqueda pública `/search` continúa devolviendo similitud semántica; el chat usa
la recuperación híbrida internamente.

Ollama ejecuta `qwen3:4b` local con contexto 4096, temperatura 0 y salida JSON
estructurada. No se ofrecen herramientas al modelo. Cada pregunta recupera hasta
cuatro fragmentos y admite hasta tres citas. Una sola generación se ejecuta a la vez.
El cliente HTTP ignora proxies del entorno, rechaza URLs remotas y no sigue redirecciones.

Para este MVP la respuesta es **extractiva**: el modelo selecciona citas y el código
comprueba que cada una existe literalmente en su fuente antes de mostrarla.
Las líneas se calculan sobre ese texto real. No se muestran explicaciones libres del
modelo ni comandos nuevos; no es todavía un asistente que sintetice libremente.
Una cita válida demuestra procedencia, pero no garantiza que responda correctamente
a la pregunta. La pertinencia y la abstención dependen del modelo y requieren ampliar
las evaluaciones con más casos. No se garantiza resistencia absoluta a prompt injection.

Documentos sin evidencia, citas inventadas o referencias inexistentes producen
abstención. Instrucciones en documentos se tratan como datos no confiables. El chat
no ejecuta procedimientos, escribe repositorios, modifica producción ni conoce credenciales.
La escucha sigue siendo localhost, sin autenticación ni permisos multiempresa todavía.

## Verificación realizada

- 39 pruebas automatizadas pasaron; Ruff y comprobación de dependencias correctos.
- Ollama portable 0.40.12, Qwen3 4B cuantizado. El log confirmó 37/37 capas en RTX 4060.
- E5, Qdrant y Ollama reales: el error 504 respondió con los 10 segundos documentados.
- El cURL coincide literalmente con el archivo de órdenes.
- Endpoint DELETE y contraseña SFTP no documentados: abstención, sin fuentes inventadas.
- Una prueba real con instrucciones maliciosas en un documento produjo abstención.
- Persiste la advertencia de deprecación HTTPX/Starlette en el cliente de pruebas.

Para repetir las comprobaciones reales, detén FastAPI para liberar Qdrant:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts/verify_chat.py
```

Esto completa el chat básico de la Fase 1. Interfaz web, sincronización automática,
autenticación, formatos adicionales y despliegue empresarial siguen pendientes.
