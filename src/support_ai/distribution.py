"""Build a small source distribution; never walk caches or unreviewed knowledge."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

from support_ai.guide import GuideError, GuideWorkspace

ROOT_FILES = (
    "catalogs.json",
    "pyproject.toml",
    "requirements-lite.txt",
    "requirements-lock.txt",
    "requirements-rag-lock.txt",
    "README.md",
    ".gitignore",
    "Abrir Support AI.cmd",
    "Instalar Support AI.cmd",
)
SOURCE_FOLDERS = (
    "src/support_ai", "scripts", "docs", "templates", "examples", "tests", "deletions",
)
EXTENSIONS = {".py", ".ps1", ".md", ".txt", ".css", ".js", ".html", ".json", ".toml"}


def application_package(root: Path, workspace: GuideWorkspace) -> bytes:
    if not (root / "pyproject.toml").is_file():
        raise GuideError("Para compartir la aplicación utiliza su carpeta de código fuente.")
    files = {}
    for name in ROOT_FILES:
        path = root / name
        if path.is_file() and not path.is_symlink():
            files[name] = path.read_bytes()
    for folder in SOURCE_FOLDERS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            relative = path.relative_to(root)
            if (
                not path.is_file()
                or path.suffix not in EXTENSIONS
                or any(part.startswith(".") or part == "__pycache__" for part in relative.parts)
                or any(item.is_symlink() for item in (path, *path.parents))
                or not path.resolve().is_relative_to(root.resolve())
            ):
                continue
            files[relative.as_posix()] = path.read_bytes()
    for doc in workspace.snapshot().documents:
        files["knowledge/" + doc.path] = doc.content.encode()
    if sum(map(len, files.values())) > 24_000_000:
        raise GuideError(
            "El código y la guía superan 24 MB; comparte la documentación por separado."
        )
    manifest = {
        "format": "support-ai-application-v1",
        "includes_models": False,
        "files": {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()},
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(files.items()):
            archive.writestr("SupportAI/" + name, payload)
        archive.writestr("SupportAI/distribution.json", json.dumps(manifest, ensure_ascii=False))
    return stream.getvalue()
