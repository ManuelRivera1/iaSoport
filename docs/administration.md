# Catálogos y colaboración mediante Git

Todos pueden mantener los catálogos, documentar y editar localmente. No hay inicio
 de sesión ni administrador por copia. El líder revisa el cambio en el PR.

1. Actualiza `trunk` y crea tu rama `feature/...`.
2. Documenta o edita desde la interfaz; las opciones están en **Catálogos**.
3. Incorpora los documentos a tu guía local para guardarlos en `knowledge/`.
4. Revisa el diff e incluye `knowledge/` y `catalogs.json` en el commit.
5. Sube tu rama y abre un PR hacia `trunk`; solicita revisión al líder.
6. El líder aprueba el PR y se integra siguiendo las reglas del repositorio.

Los catálogos se guardan en `catalogs.json`. Al descargar cambios de ese archivo,
 la aplicación vuelve a leerlos. Los índices y borradores de `data/` son locales.
La protección de `trunk`, los revisores y las notificaciones se configuran en el
 servicio Git; esta aplicación no los ha configurado remotamente.

Recorre proyecto, servicio, tipo y documento; abre uno y pulsa **Editar documento**.
Conserva los metadatos al principio para mantener su clasificación. Prepara la edición
 e incorpórala localmente antes de hacer tu commit. Los conflictos se detectan para
 evitar sobrescrituras. También puedes marcar un error nuevo e indicar su código.
