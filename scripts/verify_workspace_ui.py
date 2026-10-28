"""Exercise administrator catalogs, contributor edits and folders in local Edge."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "data" / "workspace-verification" / uuid.uuid4().hex[:8]
    artifacts.mkdir(parents=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, SUPPORT_AI_DB=str(artifacts / "db.sqlite"),
               SUPPORT_AI_WORKSPACE=str(artifacts), SUPPORT_AI_SEARCH_MODE="light")
    env.pop("SUPPORT_AI_REPO", None)
    url = f"http://127.0.0.1:{port}"
    log = (artifacts / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "support_ai.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=root, env=env, stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(40):
            try:
                with opener.open(url + "/health/live", timeout=2):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("No inició el servidor de prueba.")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                headless=True,
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1050})
            page.set_default_timeout(15000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            page.locator('[data-view="admin"]').click()
            expect(page.locator("#admin-controls")).to_be_visible()

            def create(category, name, project=None):
                page.locator(f'#catalog-category-tabs [data-category="{category}"]').click()
                page.locator("#catalog-new").click()
                page.locator("#catalog-name").fill(name)
                if project:
                    page.locator("#catalog-project").select_option(label=project)
                with page.expect_response("**/api/v1/catalogs") as saved:
                    page.locator('#catalog-form button[type="submit"]').click()
                assert saved.value.ok, saved.value.text()
                expect(page.locator("#catalog-list")).to_contain_text(name)

            create("projects", "admon-canales")
            create("services", "ms-canales", "admon-canales")
            create("areas", "Canales digitales")
            create("teams", "Equipo canales")
            create("types", "Diagnóstico técnico")
            page.locator("#catalog-search").fill("Diagnóstico")
            expect(page.locator(".catalog-entry")).to_have_count(1)
            page.locator(".catalog-entry").click()
            expect(page.locator("#catalog-name")).to_have_value("Diagnóstico técnico")
            expect(page.locator("#catalog-save")).to_have_text("Guardar cambios")
            expect(page.locator(".catalog-entry")).to_have_attribute("aria-pressed", "true")
            page.locator("#catalog-new").click()
            expect(page.locator("#catalog-name")).to_have_value("")
            page.locator("#catalog-search").fill("")
            page.locator("#catalog-status").select_option("inactive")
            expect(page.locator(".catalog-entry")).to_have_count(0)
            page.locator("#catalog-status").select_option("all")
            expect(page.locator(".catalog-entry")).to_have_count(6)
            page.screenshot(path=str(artifacts / "admin.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "catalog-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1050})
            print("CATÁLOGOS: disponibles sin contraseña", flush=True)

            page.route("**/api/v1/chat", lambda route: route.fulfill(json={
                "answer": "Respuesta de prueba para comprobar la navegación.",
                "sources": [], "abstained": False, "indexed_commit": "test",
            }))
            page.locator('.nav-item[data-view="chat"]').click()
            page.get_by_role("button", name="Resolver un error", exact=False).click()
            expect(page.locator("#messages")).to_contain_text("Respuesta de prueba")
            page.go_back()
            expect(page.locator("#chat-welcome")).to_be_visible()
            page.go_forward()
            expect(page.locator("#messages")).to_be_visible()
            page.locator("#chat-return").click()
            expect(page.locator("#chat-welcome")).to_be_visible()
            page.locator('.nav-item[data-view="incident"]').click()
            page.locator("#incident-name").fill("Registro sin guardar")
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.locator("#navigation-home").click()
            expect(page.locator("#incident-name")).to_have_value("Registro sin guardar")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#navigation-home").click()
            expect(page.locator("#incident-name")).to_have_value("")
            print("NAVEGACIÓN: atrás, adelante, preguntas iniciales y nuevo registro", flush=True)

            page.locator('.nav-item[data-view="editor"]').click()
            expect(page.locator('#document-form [name="error_code"]')).to_have_count(0)
            assert not page.locator("#notes-assistant").get_attribute("open")
            page.locator('[name="area"]').select_option("Canales digitales")
            page.locator('[name="name"]').fill("Borrador que debe conservarse")
            page.locator("#save").click()
            expect(page.locator("#draft-state")).to_have_text("Borrador guardado")
            page.locator('[name="name"]').fill("Cambios sin guardar")
            page.locator("#notes-assistant > summary").click()
            page.locator("#notes").fill("Apuntes que se deben limpiar al empezar de nuevo.")
            page.locator('[data-step="2"]').click()
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.locator("#start-new-document").click()
            expect(page.locator('[name="name"]')).to_have_value("Cambios sin guardar")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#start-new-document").click()
            expect(page.locator("#step-1")).to_be_visible()
            expect(page.locator('[name="name"]')).to_have_value("")
            expect(page.locator("#notes")).to_have_value("")
            expect(page.locator("#notes-assistant")).not_to_have_attribute("open", "")
            assert any(draft["data"]["name"] == "Borrador que debe conservarse"
                       for draft in page.request.get(url + "/api/v1/drafts").json())
            page.screenshot(path=str(artifacts / "knowledge-form.png"), full_page=True)
            page.locator('.nav-item[data-view="incident"]').click()
            page.locator('#incident-project').select_option("admon-canales")
            page.locator('#incident-service').select_option("ms-canales")
            page.locator('#incident-area').select_option("Canales digitales")
            page.locator('#incident-owner').select_option("Equipo canales")
            page.locator('#incident-code').fill("HTTP 400")
            page.locator('#incident-name').fill("Referencia de canal inválida")
            page.locator('#incident-symptoms').fill("La referencia del canal no existe.")
            page.locator('#incident-save').click()
            expect(page.locator("#incident-state")).to_have_text("Borrador guardado")
            assert page.request.get(url + "/api/v1/guide/proposals").json() == []
            page.locator('.nav-item[data-view="library"]').click()
            page.locator("#drafts-tab").click()
            page.locator("#library-search").fill("Referencia de canal inválida")
            page.get_by_role("heading", name="Referencia de canal inválida", exact=True).click()
            expect(page.locator("#view-incident")).to_be_visible()
            expect(page.locator("#incident-code")).to_have_value("HTTP 400")
            expect(page.locator("#incident-symptoms")).to_have_value(
                "La referencia del canal no existe.",
            )
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "incident-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1050})
            page.locator('#incident-symptoms').fill(
                "La referencia del canal no existe.\n\n"
                "```text\n## No dividir este bloque\nGET /canales\n```"
            )
            page.screenshot(path=str(artifacts / "incident-form.png"), full_page=True)
            page.locator('#incident-check').click()
            expect(page.locator('#incident-preview')).to_contain_text("En investigación")
            page.go_back()
            expect(page.locator("#incident-fields")).to_be_visible()
            page.go_forward()
            expect(page.locator("#incident-review")).to_be_visible()
            with page.expect_response("**/propose") as submitted:
                page.locator("#incident-propose").click()
            assert submitted.value.ok, submitted.value.text()
            proposal = submitted.value.json()["created"][0]
            for filename in ("procedimiento.md", "integraciones.md"):
                response = page.request.post(url + "/api/v1/guide/import-file", data={
                    "filename": filename, "content": "# Ejemplo\nContenido para revisar.",
                })
                assert response.ok, response.text()
            page.evaluate("renderProposals()")
            expect(page.locator(".pending-row")).to_have_count(3)
            page.get_by_role("heading", name=proposal["path"].split("/")[-1], exact=True).click()
            expect(page.locator("#reviewed-document")).to_be_enabled()
            expect(page.locator("#approve-proposal")).to_be_disabled()
            left = page.locator("#library-list").bounding_box()
            right = page.locator("#library-detail").bounding_box()
            assert left["x"] + left["width"] < right["x"]
            page.screenshot(path=str(artifacts / "pending-review.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "pending-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1050})
            print("DOCUMENTACIÓN: preparación local sin roles", flush=True)

            def login():
                page.locator('.nav-item[data-view="admin"]').click()
                expect(page.locator("#admin-controls")).to_be_visible()

            def approve(path):
                page.locator("#admin-review").click()
                page.get_by_role("heading", name=path.split("/")[-1], exact=True).click()
                page.locator("#reviewed-document").check()
                with page.expect_response("**/approve") as approved:
                    page.locator("#approve-proposal").click()
                assert approved.value.ok, approved.value.text()

            login()
            approve(proposal["path"])
            page.locator("#official-tab").click()
            expect(page.get_by_role(
                "button", name="Abrir carpeta admon-canales", exact=True,
            )).to_be_visible()
            page.get_by_role("button", name="Vista de lista", exact=True).click()
            expect(page.locator(".explorer-list")).to_have_count(1)
            page.get_by_role("button", name="Vista de tarjetas", exact=True).click()
            expect(page.locator(".explorer-list")).to_have_count(0)
            page.screenshot(path=str(artifacts / "explorer.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "explorer-mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1050})
            page.get_by_role("button", name="Abrir carpeta admon-canales", exact=True).click()
            page.go_back()
            expect(page.get_by_role(
                "button", name="Abrir carpeta admon-canales", exact=True,
            )).to_be_visible()
            page.go_forward()
            expect(page.get_by_role(
                "button", name="Abrir carpeta ms-canales", exact=True,
            )).to_be_visible()
            page.go_back()
            expect(page.get_by_role(
                "button", name="Abrir carpeta admon-canales", exact=True,
            )).to_be_visible()
            for name in ("admon-canales", "ms-canales", "Error o incidente"):
                page.get_by_role("button", name="Abrir carpeta " + name, exact=True).click()
            page.screenshot(path=str(artifacts / "folders.png"), full_page=True)
            page.get_by_role("heading", name="Referencia de canal inválida", exact=True).click()
            expect(page.locator("#library-detail")).to_contain_text("HTTP 400")
            original_content = page.request.get(
                url + "/api/v1/knowledge/snapshot"
            ).json()["documents"][0]["content"]
            print("CARPETAS: proyecto / servicio / tipo / documento", flush=True)

            page.locator('.nav-item[data-view="admin"]').click()
            page.locator('.nav-item[data-view="library"]').click()
            page.locator("#library-search").fill("Referencia de canal inválida")
            page.get_by_role("heading", name="Referencia de canal inválida", exact=True).click()
            page.get_by_role("button", name="Editar documento", exact=True).click()
            detail = page.locator("#library-detail")
            for label, value in {
                "Proyecto": "admon-canales", "Servicio": "ms-canales", "Tipo": "incident",
                "Área": "Canales digitales", "Responsable": "Equipo canales",
                "Código de error": "HTTP 400",
            }.items():
                expect(detail.get_by_label(label, exact=True)).to_have_value(value)
            page.locator(".edit-section").filter(
                has=page.get_by_text("Síntomas y cuándo ocurre", exact=True)
            ).evaluate("section => section.open = true")
            editor = page.get_by_role("textbox", name="Síntomas y cuándo ocurre", exact=True)
            editor.fill(editor.input_value().replace("no existe", "está deshabilitada"))
            unsaved_content = editor.input_value()
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.go_back()
            expect(editor).to_have_value(unsaved_content)
            page.screenshot(path=str(artifacts / "edit-sections.png"), full_page=True)
            with page.expect_response("**/approve") as saved:
                with page.expect_response("**/api/v1/guide/edit") as edited:
                    page.get_by_role("button", name="Guardar cambios locales").click()
            assert edited.value.ok, edited.value.text()
            assert saved.value.ok, saved.value.text()
            expect(page.get_by_role("button", name="Guardar cambios locales")).to_have_count(0)
            expect(page.locator("#library-detail")).to_contain_text("está deshabilitada")
            expect(page.locator("#official-tab")).to_have_class("active")
            snapshot = page.request.get(url + "/api/v1/knowledge/snapshot").json()
            assert "está deshabilitada" in snapshot["documents"][0]["content"]
            assert snapshot["documents"][0]["content"] == original_content.replace(
                "no existe", "está deshabilitada"
            )
            print("EDICIÓN: disponible para todos; ruta conservada", flush=True)
            with page.expect_response("**/api/v1/guide/delete") as requested:
                page.get_by_role("button", name="Eliminar documento", exact=True).click()
            assert requested.value.ok
            expect(page.locator("#deletions-tab")).to_have_class("active")
            expect(page.locator("#deletion-reason")).to_be_visible()
            assert page.request.get(url + "/api/v1/knowledge/snapshot").json()["documents"]
            page.once("dialog", lambda dialog: dialog.accept())
            with page.expect_response("**/reject") as cancelled:
                page.get_by_role("button", name="Cancelar eliminación", exact=True).click()
            assert cancelled.value.ok
            page.locator("#official-tab").click()
            page.locator("#library-search").fill("Referencia de canal inválida")
            page.get_by_role("heading", name="Referencia de canal inválida", exact=True).click()
            page.get_by_role("button", name="Eliminar documento", exact=True).click()
            expect(page.locator("#deletion-reason")).to_be_visible()
            page.locator("#reviewed-document").check()
            expect(page.locator("#approve-proposal")).to_be_disabled()
            page.locator("#deletion-reason").fill(
                "Este procedimiento fue reemplazado por la guía v2.",
            )
            expect(page.locator("#approve-proposal")).to_be_disabled()
            page.locator("#deletion-confirmation").fill("ELIMINAR")
            with page.expect_response("**/approve") as deleted:
                page.locator("#approve-proposal").click()
            assert deleted.value.ok, deleted.value.text()
            assert page.request.get(url + "/api/v1/knowledge/snapshot").json()["documents"] == []
            print("ELIMINACIÓN: pestaña, cancelación, motivo y doble confirmación", flush=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('.nav-item[data-view="library"]').click()
            page.locator("#official-tab").click()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
            assert not errors, errors
            print("UI OK:", artifacts, flush=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
        log.close()


if __name__ == "__main__":
    main()
