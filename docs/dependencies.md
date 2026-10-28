# Dependencias, licencias y compatibilidad

Revisión de fuentes oficiales: 27 de octubre de 2026. Las licencias siguientes
permiten uso comercial sujeto a sus obligaciones de distribución y avisos.
No se asigna licencia al código propio sin una decisión de su propietario.

| Componente | Licencia | Uso |
| --- | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi/blob/master/LICENSE) | MIT | API actual |
| [Pydantic](https://github.com/pydantic/pydantic/blob/main/LICENSE) | MIT | Modelos actuales |
| [Uvicorn](https://github.com/encode/uvicorn/blob/main/LICENSE.md) | BSD-3-Clause | Servidor actual |
| [Git](https://github.com/git/git/blob/master/COPYING) | GPL-2.0 | Ejecutable externo; no incorporado al código Python |
| [Ollama](https://github.com/ollama/ollama/blob/main/LICENSE) | MIT | Runtime local actual |
| [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) | Apache-2.0 | LLM local actual |
| [Sentence Transformers](https://github.com/huggingface/sentence-transformers/blob/main/LICENSE) | Apache-2.0 | Embeddings locales |
| [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small/blob/main/README.md) | MIT | Pesos locales |
| [PyTorch](https://github.com/pytorch/pytorch/blob/main/LICENSE) | BSD-3-Clause | Inferencia CPU |
| [Transformers](https://github.com/huggingface/transformers/blob/main/LICENSE) | Apache-2.0 | Carga del modelo |
| [Qdrant Client](https://github.com/qdrant/qdrant-client/blob/master/LICENSE) | Apache-2.0 | Índice vectorial en modo local |
| [Qdrant Server](https://github.com/qdrant/qdrant/blob/master/LICENSE) | Apache-2.0 | Servidor previsto para despliegue posterior |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE) | MIT | Persistencia local actual, serie 2.0 |
| [SQLite](https://www.sqlite.org/copyright.html) | Dominio público | Base local mediante sqlite3 de Python |
| [PostgreSQL](https://www.postgresql.org/about/licence/) | PostgreSQL License | Persistencia prevista |

MIT/BSD requieren conservar avisos; Apache requiere conservar licencia y avisos
aplicables. Redistribuir Git u otros binarios exige revisar sus obligaciones propias.
Docker Desktop tiene términos comerciales separados: evaluar licencia en cada empresa;
en servidor Linux puede usarse Docker Engine/Compose con sus licencias respectivas.

Los rangos base de pyproject están resueltos en requirements-lock.txt; la instalación
con embeddings y Qdrant local está congelada en requirements-rag-lock.txt, con el
índice oficial de ruedas CPU de PyTorch. Se verificó en Python 3.13/Windows mediante
pruebas y búsqueda real offline. Ollama/Qwen3 también se comprobaron con el chat real;
su release y digest se conservan en data/ollama. Qdrant Server aún no está verificado.
Antes de empaquetar comercialmente se requiere inventario de transitivas, avisos y
vulnerabilidades sobre versiones e imágenes definitivas; este documento no es un SBOM.
