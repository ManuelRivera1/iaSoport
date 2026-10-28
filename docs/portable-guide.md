# Guía local y portable

## Un proyecto por persona

Cada copia tiene su interfaz local y su carpeta `knowledge/`. Organiza documentos por
proyecto, área y tema. El formulario admite proyectos, servicios, APIs, incidentes y
procedimientos, con campos para autenticación, CORS y configuración. Los documentos
Markdown pueden contener diagramas Mermaid y ejemplos de solicitudes y respuestas.

La IA ayuda a ordenar las notas aportadas. Las causas de errores deben estar
documentadas: un 400 no implica por sí mismo un problema de autenticación.
El chat responde con citas comprobadas; si falta evidencia, lo indica.

## Qué ocurre al cambiar información

1. Escribes un borrador, importas un archivo o editas `knowledge/`.
2. El cambio aparece en **Por revisar**. Los archivos se comprueban cada 15 segundos
   mientras la aplicación permanece abierta.
3. Comparas la versión anterior y marcas la revisión.
4. Incorporas el cambio localmente; se guarda una versión local y se actualiza el buscador.

Consulta [administración y edición](administration.md) para configurar los catálogos,
documentar errores y recorrer la biblioteca por proyecto, servicio y tipo.

También se detectan archivos eliminados; quitar información requiere aprobación.
Si el mismo documento cambió desde que se preparó una propuesta, la aplicación
rechaza sobrescribirlo: vuelve a revisar el contenido actual.

El historial está en `data/guide-history.git`, un repositorio local sin remotos.
No modifica el historial Git del código ni necesita acceso a otros proyectos.
Los borradores se guardan en SQLite y se excluyen de los paquetes compartidos.
La actualización conserva la documentación aprobada del ejemplo local anterior
y migra los borradores al espacio de la guía.

## Importar y compartir

Puedes importar Markdown, TXT y JSON. OpenAPI conserva métodos, rutas, servidores,
seguridad y descripciones de respuestas; Postman se conserva como JSON documentado.
No se ejecuta código ni se siguen enlaces de esos archivos.

**Mi guía** contiene documentos aprobados y un manifiesto con hashes. Al recibirla,
cada documento añadido o modificado se convierte en propuesta. Reimportar el mismo
contenido no lo duplica. Un archivo ausente del paquete no elimina el documento
del destinatario: las eliminaciones se revisan en la copia local.

**Aplicación sin modelos** contiene código, instalador y guía aprobada. Excluye
`data/`, `.venv`, cachés y modelos. El destinatario instala sus dependencias una vez.
No es un ejecutable autónomo: requiere Git y Python 3.12 o 3.13.

Límites: 500 documentos, 512 KB por documento, 16 MB de texto por guía y 24 MB de
archivos antes de comprimir la aplicación. Los ZIP se validan sin extraer rutas
arbitrarias al disco.

## Búsqueda y tamaño

La búsqueda predeterminada utiliza términos sobre los fragmentos indexados.
No carga PyTorch, Sentence Transformers ni Qdrant. Resulta útil para nombres de
servicios, rutas y códigos; los sinónimos pueden requerir reformular la pregunta.
Los fragmentos demasiado grandes se omiten del contexto: estructura documentos con
encabezados y ejemplos acotados. El modo semántico anterior es opcional mediante
`SUPPORT_AI_SEARCH_MODE=semantic` y las dependencias RAG.

El modelo `qwen3:4b` y Ollama siguen ocupando varios GB por equipo. El instalador
reutiliza una instalación disponible y descarga lo que falta. La optimización
evita distribuir esos GB en cada entrega del proyecto.

Abre **Abrir Support AI.cmd** y cierra su terminal con Ctrl+C al terminar.
La aplicación escucha en localhost para uso individual. Para respaldar borradores
y trabajo en curso, conserva también `data/`: los paquetes llevan solo aprobaciones.
