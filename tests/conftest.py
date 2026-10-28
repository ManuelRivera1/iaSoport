import subprocess
from pathlib import Path

import pytest


def run(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def repo(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    run(source, "init", "-b", "main")
    run(source, "config", "user.email", "test@example.invalid")
    run(source, "config", "user.name", "Test")
    (source / "service.md").write_text("# Servicio\nGET /demo", encoding="utf-8")
    (source / "ignore.txt").write_text("ignored", encoding="utf-8")
    run(source, "add", ".")
    run(source, "-c", "core.hooksPath=", "commit", "-m", "fixture")
    return source
