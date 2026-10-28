import hashlib

import pytest
from conftest import run
from fastapi.testclient import TestClient

from support_ai.chunking import chunk_document
from support_ai.git_reader import Document, read_snapshot
from support_ai.ingestion import KnowledgeIndex
from support_ai.main import create_app


def commit(repo):
    run(repo, "add", "-A")
    run(repo, "-c", "core.hooksPath=", "commit", "-m", "update")


def test_incremental_lifecycle_and_persistence(repo, tmp_path):
    db = tmp_path / "index.db"
    with TestClient(create_app(repo, "main", db)) as client:
        assert client.get("/api/v1/knowledge/status").json()["indexed_commit"] is None
        first = client.post("/api/v1/knowledge/sync").json()
        assert first["added"] == 1
        before = client.get("/api/v1/knowledge/chunks").json()
        repeat = client.post("/api/v1/knowledge/sync").json()
        assert repeat["chunks_created"] == 0
        assert repeat["unchanged"] == 1
        assert client.get("/api/v1/knowledge/chunks").json() == before

        (repo / "other.md").write_text("# Otro\nGET /other", encoding="utf-8")
        commit(repo)
        added = client.post("/api/v1/knowledge/sync").json()
        assert added["added"] == added["unchanged"] == 1
        current = client.get("/api/v1/knowledge/chunks").json()
        original = next(c for c in current["items"] if c["path"] == "service.md")
        assert original["id"] == before["items"][0]["id"]
        assert original["commit"] == added["commit"]

        (repo / "service.md").write_text("# Servicio\nGET /new", encoding="utf-8")
        (repo / "other.md").unlink()
        commit(repo)
        result = client.post("/api/v1/knowledge/sync").json()
        assert result["modified"] == result["deleted"] == 1
        current = client.get("/api/v1/knowledge/chunks").json()
        assert current["total"] == 1
        assert "GET /new" in current["items"][0]["content"]
        assert current["items"][0]["id"] != original["id"]

    with TestClient(create_app(repo, "main", db)) as restarted:
        assert restarted.get("/api/v1/knowledge/chunks").json() == current
        assert restarted.get("/api/v1/knowledge/status").json()["documents"] == 1


def test_failed_ingestion_keeps_previous_generation(repo, tmp_path):
    with TestClient(create_app(repo, "main", tmp_path / "index.db")) as client:
        client.post("/api/v1/knowledge/sync").raise_for_status()
        previous = client.get("/api/v1/knowledge/chunks").json()
        # First path is written before the second fails: transaction must roll it back.
        (repo / "a-valid.md").write_text("# Nuevo\nValid document", encoding="utf-8")
        (repo / "z-secret.md").write_text(
            "-----BEGIN PRIVATE KEY-----\nfake-test-key", encoding="utf-8",
        )
        (repo / "service.md").unlink()
        commit(repo)
        assert client.post("/api/v1/knowledge/sync").status_code == 503
        assert client.get("/api/v1/knowledge/chunks").json() == previous
        status = client.get("/api/v1/knowledge/status").json()
        assert status["last_error"] and status["indexed_commit"] == previous["indexed_commit"]
        (repo / "z-secret.md").unlink()
        commit(repo)
        client.post("/api/v1/knowledge/sync").raise_for_status()
        assert client.get("/api/v1/knowledge/status").json()["last_error"] is None


def test_pagination_and_validation(repo, tmp_path):
    with TestClient(create_app(repo, "main", tmp_path / "index.db")) as client:
        client.post("/api/v1/knowledge/sync").raise_for_status()
        assert client.get("/api/v1/knowledge/chunks?offset=1&limit=1").json()["items"] == []
        assert client.get("/api/v1/knowledge/chunks?offset=-1").status_code == 422
        assert client.get("/api/v1/knowledge/chunks?limit=201").status_code == 422


def test_source_isolation(repo, tmp_path):
    db = tmp_path / "index.db"
    main = KnowledgeIndex(repo, "main", db)
    alternate = KnowledgeIndex(repo, "other-branch", db)
    try:
        main.sync()
        assert alternate.status().documents == 0
        assert alternate.list_chunks().items == []
    finally:
        main.close()
        alternate.close()


def test_uncommitted_changes_are_not_indexed(repo, tmp_path):
    with TestClient(create_app(repo, "main", tmp_path / "index.db")) as client:
        (repo / "service.md").write_text("uncommitted", encoding="utf-8")
        client.post("/api/v1/knowledge/sync").raise_for_status()
        content = client.get("/api/v1/knowledge/chunks").json()["items"][0]["content"]
        assert "GET /demo" in content


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_chunk_lines_preserve_fenced_commands(newline):
    lines = ["# API", "", "Texto", "", "## Comando", "```sh", "curl localhost/demo",
             "", "# This is inside code", "```", "", "## Otra sección", "Final"]
    content = newline.join(lines)
    document = Document(path="api.md", commit="abc", sha256="hash", content=content)
    pieces = chunk_document(document)
    command = next(piece for piece in pieces if "curl" in piece.content)
    assert "# This is inside code" in command.content
    assert command.content.count("```") == 2
    for piece in pieces:
        assert piece.content == "".join(
            content.splitlines(keepends=True)[piece.start_line - 1:piece.end_line],
        )
    assert "".join(piece.content for piece in pieces) == content


def test_chunker_honors_paragraph_boundaries_and_stable_ids(repo):
    document = read_snapshot(repo).documents[0]
    content = ("paragraph " * 60 + "\n\n") * 8
    document = document.model_copy(update={
        "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest(),
    })
    pieces = chunk_document(document)
    assert len(pieces) > 1
    assert all(len(piece.content) <= 1400 for piece in pieces)
    assert pieces == chunk_document(document)
