"""Browser acceptance using local Edge, real Ollama and an isolated draft database."""

import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "data" / "ui-verification"
    artifacts.mkdir(parents=True, exist_ok=True)
    guide_root = artifacts / "portable-guide"
    knowledge = guide_root / "knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    for source in (root / "examples" / "knowledge").glob("*.md"):
        target = knowledge / source.name
        if not target.exists():
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = dict(
        os.environ,
        SUPPORT_AI_DB=str(artifacts / "drafts.db"),
        SUPPORT_AI_QDRANT_PATH=str(artifacts / "unused-qdrant"),
        SUPPORT_AI_WORKSPACE=str(guide_root),
        SUPPORT_AI_SEARCH_MODE="light",
    )
    env.pop("SUPPORT_AI_REPO", None)
    log = (artifacts / "server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "support_ai.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root,
        env=env,
        stdout=log,
        stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(40):
            try:
                with opener.open(url + "/health/live", timeout=2):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("El servidor de prueba no inició.")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                headless=True,
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(180000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.get_by_role("heading", name="¿En qué te ayudamos hoy?")).to_be_visible()
            page.screenshot(path=str(artifacts / "chat.png"), full_page=True)
            page.locator('.nav-item[data-view="editor"]').click()
            page.locator("#notes-assistant > summary").click()
            page.get_by_role("button", name="Probar con un ejemplo ficticio").click()
            with page.expect_response(
                "**/api/v1/documentation/organize",
                timeout=180000,
            ) as organized:
                page.get_by_role("button", name="Completar campos con mis notas").click()
            assert organized.value.ok, organized.value.text()
            print(
                "ORGANIZED",
                organized.value.json()["data"]["name"],
                organized.value.json()["data"]["purpose"],
            )
            expect(page.locator('[name="name"]')).to_have_value("ms-payment", timeout=15000)
            expect(page.locator('[name="area"]')).to_have_value("Pagos", timeout=15000)
            assert page.locator('[name="purpose"]').input_value()
            print("AUTODOC", "notas organizadas por Ollama real")
            name = "ms-ui-" + uuid.uuid4().hex[:8]
            page.locator('[name="name"]').fill(name)
            page.locator('[data-step="2"]').click()
            page.locator(".extra-fields > summary").click()
            page.locator('[name="errors"]').fill(
                'Error de prueba. <img src=x onerror="window.injected=true">',
            )
            page.locator('[data-step="3"]').click()
            expect(page.locator("#document-preview")).to_contain_text("<img src=x")
            assert page.evaluate("window.injected === undefined")
            page.screenshot(path=str(artifacts / "document.png"), full_page=True)
            page.get_by_role("button", name="Guardar borrador", exact=True).click()
            expect(page.locator("#draft-state")).to_have_text("Borrador guardado")
            page.reload()
            page.locator('.nav-item[data-view="library"]').click()
            page.get_by_role("button", name="Mis borradores", exact=True).click()
            page.locator("#library-search").fill(name)
            page.get_by_role("button").filter(has=page.get_by_role("heading", name=name)).click()
            expect(page.locator('[name="name"]')).to_have_value(name)
            print("DRAFT", "guardado, recarga y edición; contenido HTML tratado como texto")
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('.nav-item[data-view="chat"]').click()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            with page.expect_response("**/api/v1/workspace/prepare", timeout=180000) as prepared:
                page.locator("#prepare").click()
            assert prepared.value.ok, prepared.value.text()
            expect(page.locator("#prepare")).to_be_enabled(timeout=15000)
            page.locator("#question").fill("¿Qué significa el error 504 en ms-payment?")
            with page.expect_response("**/api/v1/chat", timeout=180000) as answered:
                page.get_by_role("button", name="Enviar pregunta").click()
            assert answered.value.ok, answered.value.text()
            assert not answered.value.json()["abstained"], answered.value.text()
            expect(page.locator(".message:not(.user)").last).to_contain_text(
                "10 segundos",
                timeout=180000,
            )
            print("CHAT", "respuesta real con fuentes desde el navegador")
            page.locator('.nav-item[data-view="sharing"]').click()
            page.locator("#import-project").fill("Portal de ventas")
            page.locator("#import-area").fill("Órdenes")
            spec = {
                "openapi": "3.0.3",
                "info": {"title": "Órdenes UI"},
                "paths": {
                    "/orders/{id}": {
                        "get": {
                            "summary": "Consultar orden",
                            "responses": {
                                "400": {"description": "Referencia de orden incorrecta"},
                            },
                        }
                    },
                },
            }
            source_name = "api-" + uuid.uuid4().hex[:8]
            page.locator("#source-file").set_input_files(
                {
                    "name": source_name + ".json",
                    "mimeType": "application/json",
                    "buffer": json.dumps(spec).encode(),
                }
            )
            with page.expect_response("**/api/v1/guide/import-file") as imported:
                page.locator("#import-file").click()
            assert imported.value.ok, imported.value.text()
            proposal = imported.value.json()["created"][0]
            assert not any(
                doc["path"] == proposal["path"]
                for doc in page.request.get(
                    url + "/api/v1/knowledge/snapshot",
                ).json()["documents"]
            )
            page.evaluate("loadAdmin()")
            page.locator('.nav-item[data-view="library"]').click()
            page.locator("#library-search").fill("")
            page.locator("#pending-tab").click()
            page.get_by_role("heading", name=source_name + ".md", exact=True).click()
            expect(page.locator("#library-detail")).to_contain_text("GET /orders/{id}")
            expect(page.locator("#approve-proposal")).to_be_disabled()
            page.locator("#reviewed-document").check()
            with page.expect_response("**/approve") as approved:
                page.locator("#approve-proposal").click()
            assert approved.value.ok, approved.value.text()
            page.locator("#official-tab").click()
            page.locator("#project-filter").select_option("Portal de ventas")
            page.locator("#library-search").fill("Órdenes UI")
            expect(page.locator("#library-list")).to_contain_text("Órdenes UI")
            print("IMPORT_REVIEW", "OpenAPI local, aprobación y filtro por proyecto")
            page.locator('.nav-item[data-view="sharing"]').click()
            with page.expect_download() as exported:
                page.get_by_role("link", name="Descargar mi guía", exact=False).click()
            payload = Path(exported.value.path()).read_bytes()
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                assert "manifest.json" in archive.namelist()
                assert all(
                    name == "manifest.json" or name.startswith("knowledge/")
                    for name in archive.namelist()
                )
            page.locator("#package-file").set_input_files(
                {
                    "name": "guia.zip",
                    "mimeType": "application/zip",
                    "buffer": payload,
                }
            )
            with page.expect_response("**/api/v1/guide/import-package") as received:
                page.locator("#import-package").click()
            assert received.value.ok
            assert received.value.json()["created"] == []
            with page.expect_download() as application:
                page.get_by_role(
                    "link", name="Descargar aplicación sin modelos", exact=False
                ).click()
            application_bytes = Path(application.value.path()).read_bytes()
            with zipfile.ZipFile(io.BytesIO(application_bytes)) as archive:
                assert "SupportAI/requirements-lite.txt" in archive.namelist()
                assert not any("/data/" in name or "/.venv/" in name for name in archive.namelist())
            print(
                "SHARE",
                "paquete sin datos privados; app portable:",
                len(application_bytes),
                "bytes",
            )
            watched = "watch-" + uuid.uuid4().hex[:8] + ".md"
            (knowledge / watched).write_text(
                "# Cambio local\nTexto pendiente de revisión.", encoding="utf-8"
            )
            detected = False
            for _ in range(22):
                pending = page.request.get(url + "/api/v1/guide/proposals").json()
                if any(item["path"] == watched for item in pending):
                    detected = True
                    break
                time.sleep(1)
            assert detected, "El comprobador automático no detectó el archivo nuevo"
            assert not (artifacts / "unused-qdrant").exists()
            page.screenshot(path=str(artifacts / "sharing.png"), full_page=True)
            print("AUTO_REFRESH", "archivo detectado sin indexación manual; Qdrant no cargado")
            assert not errors, errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
        log.close()


if __name__ == "__main__":
    main()
