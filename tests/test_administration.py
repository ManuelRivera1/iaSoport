import json

from fastapi.testclient import TestClient

from support_ai.main import create_app


def test_catalogs_are_open_and_saved_for_git(tmp_path):
    database = tmp_path / "db.sqlite"
    root = tmp_path / "guide"
    with TestClient(create_app(database=database, guide_root=root)) as client:
        assert client.get("/api/v1/admin/session").status_code == 404
        created = client.post("/api/v1/catalogs", json={
            "category": "projects", "name": "admon-canales",
        })
        assert created.status_code == 201
        entry = created.json()
        assert any(row["id"] == entry["id"] for row in json.loads(
            (root / "catalogs.json").read_text(encoding="utf-8"),
        ))
        payload = {key: entry[key] for key in (
            "category", "name", "project_id", "active", "revision",
        )}
        payload["name"] = "admon-canales actualizado"
        assert client.put(f"/api/v1/catalogs/{entry['id']}", json=payload).status_code == 200
        assert client.put(f"/api/v1/catalogs/{entry['id']}", json=payload).status_code == 409
    with TestClient(create_app(database=database, guide_root=root)) as client:
        assert any(row["name"] == payload["name"]
                   for row in client.get("/api/v1/catalogs").json())
        rows = json.loads((root / "catalogs.json").read_text(encoding="utf-8"))
        target = next(row for row in rows if row["id"] == entry["id"])
        target["name"] = "Actualizado desde Git"
        target["revision"] += 1
        (root / "catalogs.json").write_text(json.dumps(rows), encoding="utf-8")
        assert any(row["name"] == "Actualizado desde Git"
                   for row in client.get("/api/v1/catalogs").json())


def test_anyone_can_incorporate_edit_and_reject_locally(tmp_path):
    with TestClient(create_app(database=tmp_path / "db.sqlite")) as client:
        draft = client.post("/api/v1/drafts", json={
            "project": "admon-canales", "area": "Canales", "service": "ms-canales",
            "kind": "incident", "name": "Referencia inv?lida", "is_new_error": True,
            "errors": "La referencia no existe.",
        }).json()
        proposal = client.post(f"/api/v1/drafts/{draft['id']}/propose", json={
            "revision": draft["revision"],
        }).json()["created"][0]
        assert client.post(f"/api/v1/guide/proposals/{proposal['id']}/approve",
                           json={"reviewed": True}).status_code == 200
        original = client.get("/api/v1/knowledge/snapshot").json()["documents"][0]
        edited = original["content"].replace("no existe", "est? deshabilitada")
        payload = {"path": original["path"], "base_sha256": original["sha256"], "content": edited}
        pending = client.post("/api/v1/guide/edit", json=payload).json()["created"][0]
        assert client.post(f"/api/v1/guide/proposals/{pending['id']}/approve",
                           json={"reviewed": True}).status_code == 200
        assert client.post("/api/v1/guide/edit", json=payload).status_code == 409
        changed = client.get("/api/v1/knowledge/snapshot").json()["documents"][0]
        assert changed["path"] == original["path"] and changed["content"] == edited
        rejected = client.post("/api/v1/guide/import-file", json={
            "filename": "test.md", "content": "# No incorporar todav?a",
        }).json()["created"][0]
        assert client.post(f"/api/v1/guide/proposals/{rejected['id']}/reject").status_code == 200
        assert client.get("/api/v1/guide/proposals").json() == []
