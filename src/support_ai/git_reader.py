"""Read committed blobs only; never checkout or execute repository content."""

import hashlib
import os
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel

MAX_DOCUMENT_BYTES = 512_000
MAX_FILES = 500


class RepositoryError(ValueError):
    pass


class Document(BaseModel):
    path: str
    commit: str
    sha256: str
    content: str


class Snapshot(BaseModel):
    commit: str
    documents: list[Document]


def git(repo: Path, *args: str) -> bytes:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        return subprocess.run(
            ["git", "--no-pager", "-c", "core.hooksPath=", "-C", str(repo), *args],
            check=True, capture_output=True, timeout=20, env=env,
        ).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise RepositoryError("No se pudo leer el repositorio Git configurado.") from exc


def read_snapshot(repo: Path, ref: str = "HEAD") -> Snapshot:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", ref):
        raise RepositoryError("Referencia Git inválida.")
    if not repo.is_dir():
        raise RepositoryError("Repositorio local no disponible.")
    # A tree lookup on this immutable commit cannot include working-tree changes.
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    commit_id = commit.decode("ascii").strip()
    entries = git(repo, "ls-tree", "-rz", "--full-tree", commit_id).split(b"\0")
    documents = []
    for entry in filter(None, entries):
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        try:
            path = raw_path.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RepositoryError("Las rutas de documentos deben utilizar UTF-8.") from exc
        # Skip symbolic links and submodules, even if their names end in .md.
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            continue
        if not path.lower().endswith(".md"):
            continue
        if len(documents) >= MAX_FILES:
            raise RepositoryError("El repositorio supera el límite de documentos del MVP.")
        object_id = oid.decode("ascii")
        if int(git(repo, "cat-file", "-s", object_id)) > MAX_DOCUMENT_BYTES:
            raise RepositoryError("Un documento supera el límite de 512 KB.")
        blob = git(repo, "cat-file", "blob", object_id)
        try:
            content = blob.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RepositoryError("Los documentos Markdown deben utilizar UTF-8.") from exc
        documents.append(Document(
            path=path, commit=commit_id, sha256=hashlib.sha256(blob).hexdigest(), content=content,
        ))
    return Snapshot(commit=commit_id, documents=documents)
