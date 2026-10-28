import base64
import io
import json
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from support_ai.distribution import application_package
from support_ai.guide import GuideError, GuideWorkspace, ProposalStore, digest, safe_path
from support_ai.importers import import_document
from support_ai.ingestion import KnowledgeIndex
from support_ai.light_search import LightSearch
from support_ai.main import create_app


@pytest.fixture
def guide(tmp_path):
    workspace = GuideWorkspace(tmp_path)
    workspace.folder.mkdir()
    (workspace.folder / "initial.md").write_text(
        "# Proyecto demo\n\n## Error 504\nLa pasarela respondió con timeout.",
        encoding="utf-8",
    )
    workspace.ensure()
    index = KnowledgeIndex(workspace.history, "main", tmp_path / "index.db")
    store = ProposalStore(index, workspace)
    yield workspace, index, store
    index.close()


@pytest.mark.parametrize("source", [
    {"openapi": "3.0.3", "info": []},
    {"openapi": "3.0.3", "paths": []},
    {"openapi": "3.0.3", "paths": {"/orders": {"get": None}}},
])
def test_invalid_openapi_is_reviewable_error(source):
    with pytest.raises(GuideError):
        import_document("api.json", json.dumps(source), "Demo", "API")


def test_only_reviewed_content_enters_history(guide):
    workspace, index, store = guide
    before = workspace.snapshot()
    pending = store.stage_many([("project/new.md", "# Nuevo\nGET /orders")], "test")
    assert workspace.snapshot() == before
    commit = store.approve(pending[0]["id"])
    assert workspace.snapshot().commit == commit != before.commit
    assert (workspace.folder / "project/new.md").read_text() == "# Nuevo\nGET /orders"
    index.sync()
    assert index.status().documents == 2
    assert LightSearch(index).search("orders").hits[0].source.path == "project/new.md"
    assert store.list() == []


def test_conflicts_and_local_changes_are_not_overwritten(guide):
    workspace, _, store = guide
    first = store.stage_many([("initial.md", "# Primera versión revisada")], "first")[0]
    second = store.stage_many([("initial.md", "# Otra versión revisada")], "second")[0]
    store.approve(first["id"])
    with pytest.raises(GuideError, match="guía cambió"):
        store.approve(second["id"])
    pending = store.stage_many([("initial.md", "# Cambio recibido")], "third")[0]
    (workspace.folder / "initial.md").write_text("# Edición local no revisada", encoding="utf-8")
    with pytest.raises(GuideError, match="cambios locales"):
        store.approve(pending["id"])


def test_scan_detects_but_does_not_approve_changes(guide):
    workspace, _, store = guide
    (workspace.folder / "new.md").write_text("# Nota nueva", encoding="utf-8")
    assert store.scan() == 1
    assert store.scan() == 0
    assert len(workspace.snapshot().documents) == 1


def test_deletion_requires_review_and_removes_obsolete_chunks(guide):
    workspace, index, store = guide
    index.sync()
    (workspace.folder / "initial.md").unlink()
    assert store.scan() == 1
    assert len(workspace.snapshot().documents) == 1
    pending = store.list()[0]
    assert pending["deletion"]
    store.approve(pending["id"])
    index.sync()
    assert workspace.snapshot().documents == []
    assert LightSearch(index).search("error 504").hits == []


def test_package_round_trip_review_and_no_private_files(guide, tmp_path):
    workspace, _, _ = guide
    (workspace.root / "data" / "private-model.bin").write_bytes(b"private")
    payload = workspace.export()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {"manifest.json", "knowledge/initial.md"}
    recipient = GuideWorkspace(tmp_path / "recipient")
    recipient.ensure()
    index = KnowledgeIndex(recipient.history, "main", tmp_path / "recipient.db")
    try:
        store = ProposalStore(index, recipient)
        staged = store.import_package(payload)
        assert len(staged) == 1
        assert recipient.snapshot().documents == []
        store.approve(staged[0]["id"])
        assert (
            recipient.snapshot().documents[0].content == workspace.snapshot().documents[0].content
        )
    finally:
        index.close()


@pytest.mark.parametrize(
    "path",
    [
        "../outside.md",
        "/outside.md",
        "a\\b.md",
        "a/.git/x.md",
        "C:/outside.md",
        "CON.md",
        "a//b.md",
        "x.txt",
    ],
)
def test_paths_rejected(path):
    with pytest.raises(GuideError):
        safe_path(path)


def test_bad_package_is_atomic_and_cannot_escape(guide):
    _, _, store = guide
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "support-ai-guide-v1",
                    "files": [
                        {"path": "valid.md", "sha256": digest("# Valid")},
                        {"path": "../escape.md", "sha256": digest("# Evil")},
                    ],
                }
            ),
        )
        archive.writestr("knowledge/valid.md", "# Valid")
        archive.writestr("knowledge/../escape.md", "# Evil")
    with pytest.raises(GuideError):
        store.import_package(stream.getvalue())
    assert store.list() == []


def test_openapi_import_preserves_endpoints_without_network():
    source = {
        "openapi": "3.0.3",
        "info": {"title": "Pedidos"},
        "paths": {
            "/orders/{id}": {
                "get": {
                    "summary": "Consultar orden",
                    "responses": {
                        "400": {"description": "Referencia incorrecta"},
                    },
                }
            },
        },
    }
    path, markdown = import_document("openapi.json", json.dumps(source), "Mi proyecto", "Órdenes")
    assert path.startswith("projects/mi-proyecto/ordenes/")
    assert "GET /orders/{id}" in markdown and "Referencia incorrecta" in markdown
    assert "POST /orders" not in markdown


def test_portable_application_excludes_models_and_pending_disk_files(guide):
    workspace, _, _ = guide
    root = workspace.root
    (root / "pyproject.toml").write_text("[project]\nname='example'", encoding="utf-8")
    (root / "data" / "model.bin").write_bytes(b"model")
    (root / ".env").write_text("secret", encoding="utf-8")
    (workspace.folder / "pending.md").write_text("# Not reviewed", encoding="utf-8")
    payload = application_package(root, workspace)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert "SupportAI/knowledge/initial.md" in names
        assert not any(
            "model.bin" in name or "pending.md" in name or ".env" in name for name in names
        )


def test_light_workflow_never_loads_tensor_dependencies(tmp_path):
    # Existing optional tests can import qdrant_client; check that this flow adds no ML imports.
    before = set(sys.modules)
    with TestClient(create_app(database=tmp_path / "db.sqlite", search_mode="light")) as client:
        imported = client.post(
            "/api/v1/guide/import-file",
            json={
                "filename": "support.md",
                "content": "# Soporte\nEl error 400 indica una referencia incorrecta.",
                "project": "Ventas",
                "area": "Soporte",
            },
        )
        assert imported.status_code == 200
        proposal = imported.json()["created"][0]
        assert client.get("/api/v1/knowledge/snapshot").json()["documents"] == []
        assert (
            client.post(
                f"/api/v1/guide/proposals/{proposal['id']}/approve",
                json={
                    "reviewed": False,
                },
            ).status_code
            == 422
        )
        approved = client.post(
            f"/api/v1/guide/proposals/{proposal['id']}/approve",
            json={
                "reviewed": True,
            },
        )
        assert approved.status_code == 200
        hits = client.post("/api/v1/search", json={"query": "error 400"}).json()["hits"]
        assert "referencia incorrecta" in hits[0]["source"]["content"]
        package = client.get("/api/v1/guide/export")
        assert package.status_code == 200 and package.content.startswith(b"PK")
        assert (
            client.post(
                "/api/v1/guide/import-package",
                json={
                    "payload": base64.b64encode(package.content).decode(),
                },
            ).json()["created"]
            == []
        )
    added = set(sys.modules) - before
    assert not any(
        name.split(".")[0] in ("torch", "sentence_transformers", "qdrant_client") for name in added
    )


def test_delete_requires_confirmation_and_current_version_and_updates_search(tmp_path):
    root = tmp_path / "guide"
    with TestClient(create_app(database=tmp_path / "db.sqlite", guide_root=root)) as client:
        proposal = client.post("/api/v1/guide/import-file", json={
            "filename": "retirable.md", "content": "# Retirable\nError 4999 de ejemplo.",
        }).json()["created"][0]
        client.post(f"/api/v1/guide/proposals/{proposal['id']}/approve",
                    json={"reviewed": True})
        before = client.get("/api/v1/knowledge/snapshot").json()
        document = before["documents"][0]
        payload = {"path": document["path"], "base_sha256": document["sha256"]}
        assert client.post("/api/v1/guide/delete", json={
            **payload, "base_sha256": "0" * 64,
        }).status_code == 409
        staged = client.post("/api/v1/guide/delete", json=payload)
        assert staged.status_code == 200
        assert (root / "knowledge" / document["path"]).exists()
        assert client.get("/api/v1/knowledge/snapshot").json() == before
        deletion = staged.json()["proposal"]
        url = f"/api/v1/guide/proposals/{deletion['id']}/approve"
        assert client.post(url, json={"reviewed": True}).status_code == 422
        reason = "Procedimiento reemplazado por una guía actualizada."
        assert client.post(url, json={"reviewed": True, "reason": reason}).status_code == 422
        response = client.post(url, json={
            "reviewed": True, "reason": reason, "confirmation_text": "ELIMINAR",
        })
        assert response.status_code == 200 and response.json()["commit"] != before["commit"]
        assert client.get("/api/v1/knowledge/snapshot").json()["documents"] == []
        assert not (root / "knowledge" / document["path"]).exists()
        record = json.loads((root / "deletions" / (deletion["id"] + ".json")).read_text(
            encoding="utf-8",
        ))
        assert record["reason"] == reason and record["path"] == document["path"]
        assert client.post("/api/v1/search", json={"query": "4999"}).json()["hits"] == []
        assert client.post("/api/v1/guide/delete", json=payload).status_code == 404
