# Interfaz local: preguntar, documentar y consultar

## Abrir

Cierra la ventana de la API anterior con Ctrl+C. Haz doble clic en
`Abrir Support AI.cmd`, en la carpeta del proyecto. Se inicia el servicio local y
se abre el navegador en `http://127.0.0.1:8000`. Deja la ventana de arranque abierta.
El arranque utiliza los modelos ya descargados; no publica el sitio ni instala servicios.

## Documentar sin editar Markdown

En **Documentar un microservicio**:

1. Pega lo que sabes en **Empieza con tus notas**. Puedes probar el ejemplo ficticio.
2. Pulsa **Organizar mis notas**. Ollama extrae datos en tu equipo y completa campos
   vacíos; los valores existentes no se reemplazan.
3. Completa **Identificar** y **Dar detalles**: área, nombre, responsable, propósito,
   dependencias, endpoints, errores, procedimientos y diagrama o explicación del flujo.
4. Utiliza las preguntas de la guía para detectar qué falta. Cada pregunta te lleva
   al campo correspondiente.
5. En **Revisar** ves el documento y puedes descargarlo. **Guardar borrador** permite
   retomarlo después desde **Mi documentación → Mis borradores**.

La IA organiza únicamente información presente en tus notas. Si un dato falta, el
campo permanece vacío: la guía te ayuda a completarlo, sin inventar detalles.
El diagrama se puede describir o pegar como Mermaid; en esta entrega se muestra
como texto y no se dibuja automáticamente.
Las notas originales se conservan dentro del borrador. El documento descargado
contiene las secciones editadas para revisar, no las notas originales sin verificar.

Los borradores son independientes del conocimiento oficial: guardarlos no los
incorpora a las respuestas ni hace commits. Después de revisar el documento se puede
descargar Markdown y usar el flujo Git existente. El circuito visual de aprobación
e incorporación a Git sigue pendiente, al igual que autenticación y roles.

## Preguntar y consultar

En **Preguntar al conocimiento** puedes usar preguntas sugeridas o escribir una
pregunta. Las respuestas muestran citas y fuentes desplegables.
**Actualizar conocimiento** sincroniza documentos ya confirmados en el repositorio
y prepara sus vectores con una sola acción, sin escribir comandos.
No incluye borradores en esa actualización.

**Mi documentación** permite buscar y leer archivos versionados, o retomar borradores.
Los cambios se guardan al pulsar **Guardar borrador**, con aviso antes de cerrar si
hay cambios pendientes. Si dos ventanas editan el mismo borrador, una revisión antigua
no puede sobrescribir una nueva; debe reabrirse el documento.

## Implementación

FastAPI sirve HTML, CSS y JavaScript locales, sin framework adicional, CDN ni build
de frontend. Los archivos viajan con el paquete Python. Sigue disponible el cliente
por terminal, pero ya no es necesario para el uso normal.

`documentation.py` gestiona campos, extracción por Ollama, preguntas, exportación y
borradores. La tabla `drafts` se agrega de forma aditiva al esquema local existente;
no se alteran los índices o documentos guardados anteriormente.
Se mantiene aislamiento por origen configurado y revisiones para evitar sobrescritura.
La detección básica de secretos se aplica a notas enviadas al organizador y al guardar.
Es una heurística, no una garantía de ausencia de datos sensibles.

El navegador inserta texto con `textContent` y no interpreta HTML de documentos o
notas. Se incluyen Content Security Policy y comprobación de Origin en escrituras.
Estas medidas no sustituyen autenticación: mantener la escucha en localhost y datos
ficticios mientras no se implemente el control de acceso.

La organización usa referencias a frases originales: el modelo clasifica sus IDs
y el servidor recupera el texto de las notas. Las etiquetas explícitas como Área,
Microservicio y Responsable también se reconocen directamente. Hay una extracción
básica de respaldo para responsabilidad, dependencias, errores y procedimientos.
No se inventan detalles para rellenar huecos. Si una selección supera el límite de
un campo, ese campo queda vacío y las notas originales siguen disponibles para editar.

## Comprobar

Las pruebas de Python cubren borradores persistentes, revisiones, aislamiento,
extracción limitada a notas originales, exportación y protección contra otros orígenes.
`scripts/verify_ui.py` prueba el navegador Edge instalado con una base y colección
aisladas, sin tocar borradores del usuario. Usa Ollama y embeddings reales, y conserva
capturas en `data/ui-verification`. Requiere Playwright, solo como herramienta de QA.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe scripts/verify_ui.py
```

Verificado en este equipo: 45 pruebas de Python pasaron, Ruff y comprobación de
dependencias correctos, JavaScript sin errores de sintaxis. Edge comprobó la
organización real de notas con Ollama, guardado y reapertura después de recargar,
vista móvil sin desbordamiento horizontal y respuesta real del chat con fuentes.
El texto HTML de prueba se mostró literalmente, sin ejecutar código.
Permanece la advertencia conocida de deprecación HTTPX/Starlette en las pruebas.
