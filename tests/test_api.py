import pytest
from conftest import run
from fastapi.testclient import TestClient

from support_ai.git_reader import RepositoryError, read_snapshot
from support_ai.main import create_app


def test_health_without_dependencies(tmp_path):
    client = TestClient(create_app(tmp_path / "missing"))
    assert client.get("/health/live").json()["status"] == "ok"
    assert client.get("/api/v1/knowledge/snapshot").status_code == 503


def test_committed_content_and_provenance(repo):
    (repo / "service.md").write_text("uncommitted", encoding="utf-8")
    (repo / "new.md").write_text("untracked", encoding="utf-8")
    response = TestClient(create_app(repo, "main")).get("/api/v1/knowledge/snapshot")
    assert response.status_code == 200
    data = response.json()
    assert data["commit"] == run(repo, "rev-parse", "HEAD")
    assert len(data["documents"]) == 1
    doc = data["documents"][0]
    assert doc["path"] == "service.md"
    assert doc["commit"] == data["commit"]
    assert "GET /demo" in doc["content"]
    assert len(doc["sha256"]) == 64


def test_deleted_document_disappears(repo):
    previous = read_snapshot(repo)
    run(repo, "rm", "service.md")
    run(repo, "-c", "core.hooksPath=", "commit", "-m", "remove")
    current = read_snapshot(repo)
    assert current.documents == []
    assert current.commit != previous.commit


def test_ref_cannot_inject_options(repo):
    with pytest.raises(RepositoryError):
        read_snapshot(repo, "--output=evil")


def test_document_limit(repo):
    (repo / "large.md").write_bytes(b"x" * 512_001)
    run(repo, "add", ".")
    run(repo, "-c", "core.hooksPath=", "commit", "-m", "large")
    with pytest.raises(RepositoryError, match="512 KB"):
        read_snapshot(repo)


def test_invalid_utf8_is_controlled(repo):
    (repo / "bad.md").write_bytes(b"\xff\xfe")
    run(repo, "add", ".")
    run(repo, "-c", "core.hooksPath=", "commit", "-m", "bad encoding")
    response = TestClient(create_app(repo, "main")).get("/api/v1/knowledge/snapshot")
    assert response.status_code == 503
    assert "UTF-8" in response.json()["detail"]
