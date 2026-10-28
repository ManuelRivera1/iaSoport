import json

import httpx
import pytest
from fastapi.testclient import TestClient

from support_ai.documentation import (
    DraftError,
    DraftStore,
    LocalNotesOrganizer,
    ServiceForm,
    missing_questions,
    to_markdown,
)
from support_ai.ingestion import KnowledgeIndex
from support_ai.main import create_app


def test_incident_has_specific_sections_and_does_not_assume_a_cause():
    data = ServiceForm(
        kind="incident", area="Canales", name="No se puede crear un canal",
        incident_symptoms="La solicitud devuelve HTTP 400.", error_code="HTTP 400",
        incident_environment="Pruebas",
    )
    markdown = to_markdown(data)
    assert "## Síntomas y cuándo ocurre" in markdown
    assert "Estado: En investigación" in markdown and "Ambiente: Pruebas" in markdown
    assert "## Causa confirmada\n\nPendiente de confirmar." in markdown
    assert "## Qué hace y para qué sirve" not in markdown
    assert "Código de error:" not in to_markdown(ServiceForm(area="Canales", name="Guía"))


def test_incident_draft_persists_and_resolved_requires_solution(tmp_path):
    with TestClient(create_app(database=tmp_path / "incident.sqlite")) as client:
        draft = client.post("/api/v1/drafts", json={
            "kind": "incident", "is_new_error": True, "area": "Canales", "name": "Error 400",
            "incident_symptoms": "No se puede crear el canal.",
            "incident_status": "resolved", "incident_environment": "Pruebas",
        }).json()
        restored = client.get(f"/api/v1/drafts/{draft['id']}").json()
        assert restored["data"]["incident_symptoms"] == "No se puede crear el canal."
        assert client.post(f"/api/v1/drafts/{draft['id']}/propose", json={
            "revision": draft["revision"],
        }).status_code == 422
        restored["data"]["incident_solution"] = "Actualizar la referencia de canal válida."
        changed = client.put(f"/api/v1/drafts/{draft['id']}", json={
            "revision": draft["revision"], "data": restored["data"],
        }).json()
        assert client.post(f"/api/v1/drafts/{draft['id']}/propose", json={
            "revision": changed["revision"],
        }).status_code == 200


def test_form_draft_persists_and_does_not_enter_official_knowledge(repo, tmp_path):
    database = tmp_path / "drafts.db"
    with TestClient(create_app(repo, "main", database)) as client:
        original = client.get("/api/v1/knowledge/snapshot").json()
        response = client.post("/api/v1/drafts", json={
            "area": "Pagos", "name": "ms-test", "purpose": "Consulta pagos.",
        })
        assert response.status_code == 201
        saved = response.json()
        assert saved["revision"] == 1
        assert "## Errores" in saved["markdown"]
        assert any(item["field"] == "errors" for item in saved["questions"])
        assert client.get("/api/v1/knowledge/snapshot").json() == original
        update = client.put(f"/api/v1/drafts/{saved['id']}", json={
            "revision": 1, "data": {**saved["data"], "errors": "Error ficticio revisado."},
        })
        assert update.status_code == 200 and update.json()["revision"] == 2
        conflict = client.put(f"/api/v1/drafts/{saved['id']}", json={
            "revision": 1, "data": saved["data"],
        })
        assert conflict.status_code == 409
    with TestClient(create_app(repo, "main", database)) as client:
        assert client.get("/api/v1/drafts").json()[0]["data"]["errors"]
        assert client.get("/api/v1/drafts/missing").status_code == 404


def test_drafts_are_separated_by_source(repo, tmp_path):
    first = KnowledgeIndex(repo, "main", tmp_path / "db.sqlite")
    other = KnowledgeIndex(repo, "another", tmp_path / "db.sqlite")
    try:
        saved = DraftStore(first).save(ServiceForm(area="A", name="Service"))
        assert DraftStore(other).list() == []
        with pytest.raises(DraftError):
            DraftStore(other).get(saved.id)
    finally:
        first.close()
        other.close()


def test_empty_or_credential_drafts_rejected(tmp_path):
    with TestClient(create_app(database=tmp_path / "db.sqlite")) as client:
        assert client.post("/api/v1/drafts", json={"name": "missing area"}).status_code == 422
        assert client.post("/api/v1/drafts", json={
            "area": "A", "name": "B", "notes": "-----BEGIN PRIVATE KEY-----",
        }).status_code == 422


def test_organizer_keeps_only_literal_notes(monkeypatch):
    original_client = httpx.Client
    notes = "ms-payment consulta pagos. El error 504 indica un timeout."

    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == "qwen3:4b"
        generated = {key: [] for key in (
            "area", "name", "topic", "owner", "purpose", "dependencies",
            "api", "errors", "procedures", "diagram",
        )}
        generated.update(name=[1], purpose=[1], api=[999], errors=[2])
        return httpx.Response(200, json={"done": True, "message": {
            "content": json.dumps(generated),
        }})

    monkeypatch.setattr("support_ai.documentation.httpx.Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handle), **kwargs,
    ))
    result = LocalNotesOrganizer().organize(notes)
    assert "ms-payment" in result.name and "consulta pagos." in result.purpose
    assert result.api == "" and result.notes == notes


def test_guidance_and_export_are_editable_text():
    data = ServiceForm(area="A", name="B", api="GET /valid", notes="Unverified original note")
    assert "GET /valid" in to_markdown(data)
    assert "Unverified original note" not in to_markdown(data)
    assert any(item["field"] == "purpose" for item in missing_questions(data))


def test_web_assets_and_cross_origin_write_protection(tmp_path):
    with TestClient(create_app(database=tmp_path / "db.sqlite")) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert 'id="view-editor"' in response.text
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/assets/styles.css").status_code == 200
        assert client.post("/api/v1/drafts", json={"area": "A", "name": "B"}, headers={
            "Origin": "https://untrusted.invalid",
        }).status_code == 403
        assert client.post("/api/v1/drafts", json={"area": "A", "name": "B"}, headers={
            "Origin": "http://testserver",
        }).status_code == 201
