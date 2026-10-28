"""Portable Markdown guide with private local Git history and explicit review."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import unicodedata
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from threading import RLock

from sqlalchemy import insert, select, update

from support_ai.git_reader import MAX_FILES, RepositoryError, read_snapshot
from support_ai.ingestion import SECRET_PATTERNS, KnowledgeIndex
from support_ai.storage import proposals

MAX_FILE = 512_000
MAX_PACKAGE = 16_000_000


class GuideError(ValueError):
    pass


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def safe_path(value: str) -> str:
    parts = PurePosixPath(value).parts
    if (
        not parts
        or value.startswith(("/", "\\"))
        or "\\" in value
        or any(part in (".", "..") or part.startswith(".") or ":" in part for part in parts)
        or not value.lower().endswith(".md")
        or len(value) > 220
        or any(char in value for char in "\x00\n\r\t")
    ):
        raise GuideError("La ruta del documento no es válida.")
    # Keep path spelling canonical, including Windows case-insensitive destinations.
    if "/".join(parts) != value or any(re.search(r'[<>"|?*]|[. ]$', p) for p in parts):
        raise GuideError("La ruta del documento no es válida.")
    if any(
        part.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"COM{i}" for i in range(10)],
            *[f"LPT{i}" for i in range(10)],
        }
        for part in parts
    ):
        raise GuideError("Nombre de archivo reservado.")
    return value


def slug(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9_-]+", "-", plain).strip("-")[:48] or "general"


def validate_content(content: str) -> None:
    if not content.strip() or len(content.encode("utf-8")) > MAX_FILE:
        raise GuideError("El documento está vacío o supera 512 KB.")
    if "\x00" in content or any(pattern.search(content) for pattern in SECRET_PATTERNS):
        raise GuideError("El documento contiene datos binarios o posibles credenciales.")


class GuideWorkspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.folder = self.root / "knowledge"
        self.history = self.root / "data" / "guide-history.git"
        self.lock = RLock()
        self._snapshot_cache = None
        self._disk_cache = {}

    def _git(self, *args: str, data: bytes | None = None, index: str | None = None) -> str:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
        if index:
            env["GIT_INDEX_FILE"] = index
        command = [
            "git",
            "-c",
            "core.hooksPath=",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=Support AI local",
            "-c",
            "user.email=local@example.invalid",
            "-C",
            str(self.history),
            *args,
        ]
        try:
            return (
                subprocess.run(
                    command, input=data, capture_output=True, check=True, timeout=30, env=env
                )
                .stdout.decode()
                .strip()
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GuideError("No se pudo actualizar el historial local de la guía.") from exc

    def snapshot(self):
        commit = self._git("rev-parse", "--verify", "refs/heads/main^{commit}")
        if self._snapshot_cache is None or self._snapshot_cache.commit != commit:
            self._snapshot_cache = read_snapshot(self.history, "main")
        return self._snapshot_cache

    def _commit(self, documents: dict[str, str], message: str, parent: str | None) -> str:
        # No checkout, repository hooks, filters or shared user index are executed.
        with tempfile.TemporaryDirectory(dir=self.history.parent) as directory:
            index = str(Path(directory) / "index")
            self._git("read-tree", "--empty", index=index)
            for path, content in sorted(documents.items()):
                safe_path(path)
                blob = self._git("hash-object", "-w", "--stdin", data=content.encode())
                self._git("update-index", "--add", "--cacheinfo", "100644", blob, path, index=index)
            tree = self._git("write-tree", index=index)
            args = ["commit-tree", tree, *(["-p", parent] if parent else [])]
            commit = self._git(*args, data=message.encode())
            self._git("update-ref", "refs/heads/main", commit, parent or "0" * 40)
            return commit

    def ensure(self):
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            if (self.history / "HEAD").is_file():
                self.snapshot()  # A damaged history is never silently replaced.
                return
            self.history.mkdir(parents=True, exist_ok=True)
            self._git("init", "--bare", "--initial-branch=main")
            files = self.disk_documents()
            legacy = self.root / "data" / "demo-knowledge"
            if legacy.is_dir():
                try:
                    files.update(
                        {doc.path: doc.content for doc in read_snapshot(legacy, "main").documents}
                    )
                except RepositoryError as exc:
                    raise GuideError(
                        "No se pudo migrar la guía anterior; se conserva intacta."
                    ) from exc
            for path, content in files.items():
                target = self.disk_path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text(content, encoding="utf-8")
            for content in files.values():
                validate_content(content)
            self._commit(files, "Inicializar guía local", None)

    def disk_path(self, path: str) -> Path:
        safe_path(path)
        target = self.folder.joinpath(*PurePosixPath(path).parts)
        for item in (self.folder, *target.parents):
            if item == self.root:
                break
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise GuideError("No se admiten enlaces en la carpeta de conocimiento.")
        if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
            raise GuideError("No se admiten enlaces en documentos.")
        if not target.resolve().is_relative_to(self.folder.resolve()):
            raise GuideError("El documento sale de la carpeta de conocimiento.")
        return target

    def disk_documents(self) -> dict[str, str]:
        documents = {}
        cache = {}
        for file in self.folder.rglob("*.md"):
            if len(documents) >= MAX_FILES:
                raise GuideError("La guía supera el límite de 500 documentos.")
            path = file.relative_to(self.folder).as_posix()
            target = self.disk_path(path)
            stat = target.stat()
            if stat.st_size > MAX_FILE:
                raise GuideError("Un documento supera 512 KB.")
            signature = (stat.st_size, stat.st_mtime_ns)
            previous = self._disk_cache.get(path)
            if previous and previous[0] == signature:
                content = previous[1]
            else:
                content = target.read_text(encoding="utf-8-sig")
                validate_content(content)
            documents[path] = content
            cache[path] = (signature, content)
        self._disk_cache = cache
        return documents

    def approve(
        self, path: str, content: str | None, base_sha256: str | None,
        deletion_record: dict | None = None,
    ) -> str:
        if content is not None:
            validate_content(content)
        with self.lock:
            snapshot = self.snapshot()
            documents = {doc.path: doc.content for doc in snapshot.documents}
            if any(old.casefold() == path.casefold() and old != path for old in documents):
                raise GuideError("Ya existe una ruta equivalente con otras mayúsculas.")
            current = digest(documents[path]) if path in documents else None
            if current != base_sha256:
                raise GuideError(
                    "La guía cambió desde que se preparó esta propuesta. Revisa la nueva versión."
                )
            if path not in documents and len(documents) >= MAX_FILES:
                raise GuideError("La guía admite hasta 500 documentos.")
            target = self.disk_path(path)
            if target.exists():
                local = target.read_text(encoding="utf-8-sig")
                if digest(local) not in (
                    base_sha256,
                    digest(content) if content is not None else None,
                ):
                    raise GuideError("Hay cambios locales más recientes. No se sobrescribieron.")
            else:
                local = None
            if content is None:
                documents.pop(path, None)
            else:
                documents[path] = content
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".pending-" + uuid.uuid4().hex)
            audit = None
            if deletion_record:
                audit = self.root / "deletions" / (deletion_record["proposal_id"] + ".json")
                if not audit.resolve().is_relative_to(self.root.resolve()):
                    raise GuideError("La carpeta de registro debe estar dentro del proyecto.")
                if audit.exists():
                    raise GuideError("Ya existe un registro para esta eliminación.")
            try:
                if audit:
                    audit.parent.mkdir(parents=True, exist_ok=True)
                    audit.write_text(
                        json.dumps(deletion_record, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                if content is None:
                    target.unlink(missing_ok=True)
                else:
                    temporary.write_text(content, encoding="utf-8")
                    temporary.replace(target)
                return self._commit(
                    documents, "Aprobar documentación revisada: " + path, snapshot.commit
                )
            except Exception:
                if audit:
                    audit.unlink(missing_ok=True)
                if local is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_text(local, encoding="utf-8")
                raise
            finally:
                temporary.unlink(missing_ok=True)

    def export(self) -> bytes:
        with self.lock:
            snapshot = self.snapshot()
            total = sum(len(doc.content.encode()) for doc in snapshot.documents)
            if total > MAX_PACKAGE:
                raise GuideError("Divide la guía: el paquete admite hasta 16 MB de texto.")
            output = io.BytesIO()
            manifest = {"format": "support-ai-guide-v1", "commit": snapshot.commit, "files": []}
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for doc in snapshot.documents:
                    validate_content(doc.content)
                    path = safe_path(doc.path)
                    archive.writestr("knowledge/" + path, doc.content.encode())
                    manifest["files"].append({"path": path, "sha256": digest(doc.content)})
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            return output.getvalue()


class ProposalStore:
    def __init__(self, index: KnowledgeIndex, workspace: GuideWorkspace):
        self.index, self.workspace = index, workspace

    def list(self, full: bool = False) -> list[dict]:
        with self.index.lock, self.index.engine.connect() as connection:
            rows = connection.execute(
                select(proposals)
                .where(
                    proposals.c.repository_id == self.index.repository_id,
                    proposals.c.status == "pending",
                )
                .order_by(proposals.c.created_at.desc())
            ).mappings()
            return [
                {
                    "deletion": row["content"] == "",
                    **{
                        key: value
                        for key, value in row.items()
                        if key != "repository_id" and (full or key != "content")
                    },
                }
                for row in rows
            ]

    def stage_many(
        self, incoming: list[tuple[str, str | None]], origin: str, allow_retry: bool = False,
    ) -> list[dict]:
        with self.workspace.lock, self.index.lock:
            official = {
                doc.path: digest(doc.content) for doc in self.workspace.snapshot().documents
            }
            for path, content in incoming:
                safe_path(path)
                if content is not None:
                    validate_content(content)
            if len({path.casefold() for path, _ in incoming}) != len(incoming):
                raise GuideError("El paquete contiene rutas duplicadas.")
            created = []
            with self.index.engine.begin() as connection:
                existing = (
                    connection.execute(
                        select(proposals).where(
                            proposals.c.repository_id == self.index.repository_id,
                            proposals.c.status.in_(("pending",) if allow_retry else (
                                "pending", "rejected",
                            )),
                        )
                    )
                    .mappings()
                    .all()
                )
                for path, content in incoming:
                    sha = digest(content or "")
                    base = official.get(path)
                    if content is None and base is None:
                        continue
                    if sha == base:
                        continue
                    if any(
                        row["path"] == path and row["sha256"] == sha and row["base_sha256"] == base
                        for row in existing
                    ):
                        continue
                    row = {
                        "id": uuid.uuid4().hex,
                        "repository_id": self.index.repository_id,
                        "path": path,
                        "content": content or "",
                        "sha256": sha,
                        "base_sha256": base,
                        "origin": origin[:240],
                        "status": "pending",
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                    connection.execute(insert(proposals).values(**row))
                    created.append(
                        {key: value for key, value in row.items() if key != "repository_id"}
                    )
            return created

    def scan(self) -> int:
        disk = self.workspace.disk_documents()
        previous = {doc.path for doc in self.workspace.snapshot().documents}
        incoming = [*disk.items(), *((path, None) for path in previous - disk.keys())]
        return len(self.stage_many(incoming, "Carpeta knowledge"))

    def reject(self, proposal_id: str):
        with self.index.lock, self.index.engine.begin() as connection:
            result = connection.execute(update(proposals).where(
                proposals.c.id == proposal_id,
                proposals.c.repository_id == self.index.repository_id,
                proposals.c.status == "pending",
            ).values(status="rejected"))
            if not result.rowcount:
                raise GuideError("No se encontró la propuesta pendiente.")

    def approve(self, proposal_id: str, reason: str = "") -> str:
        with self.workspace.lock, self.index.lock, self.index.engine.connect() as connection:
            row = (
                connection.execute(
                    select(proposals).where(
                        proposals.c.id == proposal_id,
                        proposals.c.repository_id == self.index.repository_id,
                        proposals.c.status == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise GuideError("No se encontró la propuesta pendiente.")
            # A retry after a SQL status-write failure is safe and does not duplicate commits.
            snapshot = self.workspace.snapshot()
            current = next((doc for doc in snapshot.documents if doc.path == row["path"]), None)
            if (current and digest(current.content) == row["sha256"]) or (
                current is None and row["content"] == ""
            ):
                commit = snapshot.commit
            else:
                commit = self.workspace.approve(
                    row["path"], row["content"] or None, row["base_sha256"],
                    deletion_record={
                        "proposal_id": row["id"], "path": row["path"],
                        "previous_sha256": row["base_sha256"], "reason": reason,
                        "confirmed_at": datetime.now(UTC).isoformat(),
                    } if row["content"] == "" and reason else None,
                )
        with self.index.lock, self.index.engine.begin() as connection:
            connection.execute(
                update(proposals).where(proposals.c.id == proposal_id).values(status="approved")
            )
        return commit

    def import_package(self, payload: bytes) -> list[dict]:
        if len(payload) > MAX_PACKAGE:
            raise GuideError("El paquete supera 16 MB.")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > MAX_FILES + 1
                    or sum(item.file_size for item in entries) > MAX_PACKAGE + MAX_FILE
                    or len({item.filename.casefold() for item in entries}) != len(entries)
                ):
                    raise GuideError("El paquete supera los límites o contiene rutas duplicadas.")
                if any(item.flag_bits & 1 or item.file_size > MAX_FILE for item in entries):
                    raise GuideError("No se admiten archivos cifrados o mayores de 512 KB.")
                manifest = json.loads(archive.read("manifest.json"))
                if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
                    raise GuideError("El manifiesto del paquete no es válido.")
                if manifest.get("format") != "support-ai-guide-v1":
                    raise GuideError("Formato de paquete no compatible.")
                listed = manifest["files"]
                expected = {"manifest.json"} | {
                    "knowledge/" + safe_path(item["path"]) for item in listed
                }
                if expected != {item.filename for item in entries} or len(listed) + 1 != len(
                    entries
                ):
                    raise GuideError("El manifiesto no coincide con los archivos del paquete.")
                incoming = []
                for item in listed:
                    content = archive.read("knowledge/" + item["path"]).decode("utf-8")
                    if digest(content) != item["sha256"]:
                        raise GuideError("El contenido no coincide con el checksum del paquete.")
                    incoming.append((item["path"], content))
            return self.stage_many(incoming, "Paquete compartido")
        except GuideError:
            raise
        except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
            raise GuideError("El archivo no es un paquete válido de Support AI.") from exc
