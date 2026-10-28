"""Open local catalogs; team approval belongs to the Git pull request."""

import json
import re
import uuid
from pathlib import Path
from threading import RLock
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, insert, select, update

from support_ai.git_reader import read_snapshot
from support_ai.storage import catalogs, drafts

Category = Literal["projects", "areas", "teams", "types", "services"]
DEFAULT_TYPES = {
    "project": "Guía del proyecto", "service": "Microservicio", "api": "API y endpoints",
    "incident": "Error o incidente", "procedure": "Procedimiento",
}
class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Category
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^\r\n]+$")
    project_id: str | None = Field(default=None, max_length=32)
    active: bool = True
    revision: int = Field(default=1, ge=1)


class Administration:
    def __init__(self, index, root: Path):
        self.index = index
        self.lock = RLock()
        self.path = root / "catalogs.json"

    def export(self):
        with self.index.engine.connect() as connection:
            rows = connection.execute(select(catalogs).where(
                catalogs.c.repository_id == self.index.repository_id,
            ).order_by(catalogs.c.id)).mappings().all()
            data = [{key: value for key, value in row.items() if key != "repository_id"}
                    for row in rows]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.pending")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        temporary.replace(self.path)

    def seed(self):
        with self.lock, self.index.engine.begin() as connection:
            if self.path.exists():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if not isinstance(raw, list) or len(raw) > 5000:
                        raise ValueError("Cat?logo demasiado grande o inv?lido")
                    entries = []
                    seen_ids = set()
                    for item in raw:
                        entry_id = item["id"]
                        if not re.fullmatch(r"[a-f0-9]{32}", entry_id) or entry_id in seen_ids:
                            raise ValueError("Identificador duplicado o inv?lido")
                        seen_ids.add(entry_id)
                        data = CatalogEntry.model_validate(
                            {key: value for key, value in item.items() if key != "id"},
                        )
                        entries.append({"id": entry_id, "repository_id": self.index.repository_id,
                                        **data.model_dump()})
                except (ValueError, KeyError, TypeError) as exc:
                    raise HTTPException(
                        422, "Revisa el archivo catalogs.json del proyecto.",
                    ) from exc
                connection.execute(delete(catalogs).where(
                    catalogs.c.repository_id == self.index.repository_id,
                ))
                if entries:
                    connection.execute(insert(catalogs), entries)
                return
            exists = connection.execute(select(catalogs.c.id).where(
                catalogs.c.repository_id == self.index.repository_id,
            )).first()
            if exists:
                return
            rows = [("types", label, None) for label in DEFAULT_TYPES.values()]
            legacy = []
            for doc in read_snapshot(self.index.repo, self.index.ref).documents:
                header = doc.content.split("\n## ", 1)[0]
                def field(label, header=header):
                    match = re.search(r"^" + label + r":\s*(.+)$", header, re.M)
                    return match[1].strip() if match else ""
                title = re.search(r"^# (.+)$", header, re.M)
                legacy.append({"project": field("Proyecto") or "General",
                               "area": field("Área"), "owner": field("Responsable"),
                               "service": field("Servicio") or (title[1] if title else "")})
            legacy.extend(connection.execute(select(drafts.c.data).where(
                drafts.c.repository_id == self.index.repository_id,
            )).scalars().all())
            projects = {"General", *(item.get("project", "General") for item in legacy)}
            project_ids = {name: uuid.uuid4().hex for name in projects if name}
            for name, entry_id in project_ids.items():
                connection.execute(insert(catalogs).values(
                    id=entry_id, repository_id=self.index.repository_id,
                    category="projects", name=name[:120], project_id=None, active=1,
                    revision=1,
                ))
            for item in legacy:
                rows.extend((category, item.get(field, ""), None)
                            for category, field in (("areas", "area"), ("teams", "owner")))
                rows.append(("services", item.get("service") or item.get("name", ""),
                             project_ids.get(item.get("project") or "General")))
            seen = set()
            for category, name, project_id in rows:
                key = (category, name.casefold(), project_id)
                if not name or name == "Por confirmar" or key in seen:
                    continue
                seen.add(key)
                connection.execute(insert(catalogs).values(
                    id=uuid.uuid4().hex, repository_id=self.index.repository_id,
                    category=category, name=name[:120], project_id=project_id, active=1, revision=1,
                ))

    def list(self):
        self.seed()
        with self.index.engine.connect() as connection:
            rows = connection.execute(select(catalogs).where(
                catalogs.c.repository_id == self.index.repository_id,
            ).order_by(catalogs.c.category, catalogs.c.name)).mappings()
            return [{key: value for key, value in row.items() if key != "repository_id"}
                    for row in rows]

    def save(self, data, entry_id=None):
        self.seed()
        with self.lock, self.index.engine.begin() as connection:
            rows = connection.execute(select(catalogs).where(
                catalogs.c.repository_id == self.index.repository_id,
            )).mappings().all()
            current = next((row for row in rows if row["id"] == entry_id), None)
            if entry_id and current is None:
                raise HTTPException(404, "No se encontró la opción del catálogo.")
            if current and (current["revision"] != data.revision
                            or current["category"] != data.category):
                raise HTTPException(409, "El catálogo cambió. Recarga antes de guardar.")
            if any(row["id"] != entry_id and row["category"] == data.category
                   and row["project_id"] == data.project_id
                   and row["name"].casefold() == data.name.casefold() for row in rows):
                raise HTTPException(409, "Ya existe una opción con ese nombre.")
            if data.category == "services":
                parent = next((row for row in rows if row["id"] == data.project_id
                               and row["category"] == "projects" and row["active"]), None)
                if parent is None:
                    raise HTTPException(422, "Selecciona un proyecto activo para el servicio.")
            elif data.project_id is not None:
                raise HTTPException(422, "Solo los servicios se vinculan a un proyecto.")
            values = data.model_dump(exclude={"revision"})
            values["revision"] = current["revision"] + 1 if current else 1
            if current:
                connection.execute(
                    update(catalogs).where(catalogs.c.id == entry_id).values(**values),
                )
            else:
                entry_id = uuid.uuid4().hex
                connection.execute(insert(catalogs).values(
                    id=entry_id, repository_id=self.index.repository_id, **values,
                ))
        self.export()
        return {"id": entry_id, **values}


def attach_administration(app: FastAPI, store: Administration):
    @app.get("/api/v1/catalogs")
    def list_catalogs():
        with store.lock:
            values = store.list()
            if not store.path.exists():
                store.export()
            return values

    @app.post("/api/v1/catalogs", status_code=201)
    def create_catalog(data: CatalogEntry):
        with store.lock:
            return store.save(data)

    @app.put("/api/v1/catalogs/{entry_id}")
    def update_catalog(entry_id: str, data: CatalogEntry):
        with store.lock:
            return store.save(data, entry_id)
