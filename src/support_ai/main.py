import asyncio
import base64
import hashlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from support_ai.administration import Administration, attach_administration
from support_ai.chat import ChatError, ChatRequest, ChatResponse, ChatService, Generator
from support_ai.distribution import application_package
from support_ai.documentation import (
    Draft,
    DraftError,
    DraftStore,
    DraftUpdate,
    LocalNotesOrganizer,
    NotesOrganizer,
    NotesRequest,
    ServiceForm,
    missing_questions,
)
from support_ai.embeddings import Embedder
from support_ai.git_reader import RepositoryError, Snapshot, git, read_snapshot
from support_ai.guide import (
    GuideError,
    GuideWorkspace,
    ProposalStore,
    digest,
    slug,
    validate_content,
)
from support_ai.importers import import_document
from support_ai.ingestion import (
    IndexedChunks,
    IndexStatus,
    IngestionError,
    KnowledgeIndex,
    SyncResult,
)
from support_ai.light_search import LightSearch
from support_ai.retrieval import (
    RetrievalError,
    SearchRequest,
    SearchResult,
    SemanticIndex,
    VectorizeResult,
    VectorStatus,
)
from support_ai.storage import drafts as draft_table


class FileImport(BaseModel):
    filename: str = Field(max_length=160)
    content: str = Field(max_length=512000)
    project: str = Field(default="General", max_length=120)
    area: str = Field(default="General", max_length=120)


class PackageImport(BaseModel):
    payload: str = Field(max_length=22000000)


class ReviewConfirmation(BaseModel):
    reviewed: bool
    reason: str = Field(default="", max_length=2000)
    confirmation_text: str = Field(default="", max_length=30)


class DraftProposal(BaseModel):
    revision: int = Field(ge=1)


class DocumentEdit(BaseModel):
    path: str = Field(max_length=500)
    base_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content: str = Field(min_length=1, max_length=512000)


class DocumentDelete(BaseModel):
    path: str = Field(max_length=500)
    base_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: bool = False


def create_app(
    repo: Path | None = None,
    ref: str | None = None,
    database: Path | None = None,
    vector_path: Path | None = None,
    model_path: Path | None = None,
    embedder: Embedder | None = None,
    generator: Generator | None = None,
    organizer: NotesOrganizer | None = None,
    guide_root: Path | None = None,
    search_mode: str | None = None,
    auto_refresh: bool | None = None,
) -> FastAPI:
    custom_database = database is not None
    workspace = None
    if repo is None and not os.environ.get("SUPPORT_AI_REPO"):
        root = guide_root or (
            Path(os.environ["SUPPORT_AI_WORKSPACE"])
            if os.environ.get("SUPPORT_AI_WORKSPACE")
            else database.parent / "guide-local"
            if custom_database
            else Path.cwd()
        )
        workspace = GuideWorkspace(root)
    configured_repo = repo or (
        Path(os.environ["SUPPORT_AI_REPO"])
        if os.environ.get("SUPPORT_AI_REPO")
        else workspace.history
    )
    configured_ref = ref or os.environ.get("SUPPORT_AI_REF", "main")
    database = database or Path(os.environ.get("SUPPORT_AI_DB", "data/support-ai.db"))
    index = KnowledgeIndex(configured_repo, configured_ref, database)
    mode = (
        search_mode
        or os.environ.get("SUPPORT_AI_SEARCH_MODE")
        or ("semantic" if embedder is not None else "light")
    )
    if mode not in ("light", "semantic"):
        raise ValueError("SUPPORT_AI_SEARCH_MODE debe ser light o semantic.")
    vectors = (
        SemanticIndex(
            index,
            vector_path or Path(os.environ.get("SUPPORT_AI_QDRANT_PATH", "data/qdrant")),
            model_path
            or Path(
                os.environ.get(
                    "SUPPORT_AI_EMBEDDING_MODEL",
                    "data/models/multilingual-e5-small",
                )
            ),
            embedder=embedder,
        )
        if mode == "semantic"
        else LightSearch(index)
    )
    chat = ChatService(vectors, generator)
    draft_store = DraftStore(index)
    administration = Administration(index, (workspace.root if workspace else database.parent))
    notes_organizer = organizer or LocalNotesOrganizer()
    proposal_store = ProposalStore(index, workspace) if workspace else None
    enabled_refresh = (
        auto_refresh if auto_refresh is not None else workspace is not None and not custom_database
    )
    refresh_state = {"last_error": None}

    def refresh():
        try:
            if proposal_store:
                proposal_store.scan()
            with index.lock:
                commit = (
                    git(
                        configured_repo,
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        f"{configured_ref}^{{commit}}",
                    )
                    .decode()
                    .strip()
                )
                if index.status().indexed_commit != commit:
                    index.sync()
                    if mode == "semantic":
                        vectors.vectorize()
            refresh_state["last_error"] = None
        except (
            GuideError, RepositoryError, IngestionError, RetrievalError, OSError, SQLAlchemyError,
        ) as exc:
            refresh_state["last_error"] = str(exc)

    async def refresh_loop(stop):
        while not stop.is_set():
            await asyncio.to_thread(refresh)
            try:
                await asyncio.wait_for(stop.wait(), timeout=15)
            except TimeoutError:
                pass

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        task = None
        if workspace:
            await asyncio.to_thread(workspace.ensure)
            if not custom_database:
                legacy_id = hashlib.sha256(
                    f"{(workspace.root / 'data' / 'demo-knowledge').resolve()}\0main".encode(),
                ).hexdigest()
                with index.engine.begin() as connection:
                    connection.execute(
                        update(draft_table)
                        .where(
                            draft_table.c.repository_id == legacy_id,
                        )
                        .values(repository_id=index.repository_id)
                    )
        if enabled_refresh:
            task = asyncio.create_task(refresh_loop(stop))
        try:
            yield
        finally:
            stop.set()
            if task:
                await task
            try:
                vectors.close()
            finally:
                index.close()

    app = FastAPI(
        title="Support AI",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    attach_administration(app, administration)
    web = Path(__file__).parent / "web"
    app.mount("/assets", StaticFiles(directory=web, check_dir=False), name="assets")

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and origin
            and origin.rstrip("/") != str(request.base_url).rstrip("/")
        ):
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=403, content={"detail": "Origen no permitido."})
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(web / "index.html")

    @app.get("/health/live")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/v1/knowledge/snapshot", response_model=Snapshot)
    def snapshot() -> Snapshot:
        try:
            return read_snapshot(configured_repo, configured_ref)
        except RepositoryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/v1/knowledge/sync", response_model=SyncResult)
    def sync() -> SyncResult:
        try:
            return index.sync()
        except IngestionError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/knowledge/status", response_model=IndexStatus)
    def index_status() -> IndexStatus:
        try:
            return index.status()
        except (SQLAlchemyError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Índice local no disponible.") from exc

    @app.get("/api/v1/knowledge/chunks", response_model=IndexedChunks)
    def indexed_chunks(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> IndexedChunks:
        try:
            return index.list_chunks(offset, limit)
        except (SQLAlchemyError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Índice local no disponible.") from exc

    @app.post("/api/v1/knowledge/vectorize", response_model=VectorizeResult)
    def vectorize() -> VectorizeResult:
        try:
            return vectors.vectorize()
        except RetrievalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/knowledge/vectors/status", response_model=VectorStatus)
    def vector_status() -> VectorStatus:
        try:
            if mode == "light":
                status = index.status()
                return VectorStatus(
                    indexed_commit=status.indexed_commit,
                    source_commit=status.indexed_commit,
                    chunks=status.chunks,
                    stale=status.indexed_commit is None,
                )
            return vectors.status()
        except (SQLAlchemyError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Índice vectorial no disponible.") from exc

    @app.post("/api/v1/search", response_model=SearchResult)
    def search(request: SearchRequest) -> SearchResult:
        try:
            return vectors.search(request.query, request.top_k)
        except RetrievalError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/v1/chat", response_model=ChatResponse)
    def answer(request: ChatRequest) -> ChatResponse:
        try:
            return chat.answer(request.question)
        except (ChatError, RetrievalError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/v1/workspace/prepare")
    def prepare_knowledge():
        try:
            if proposal_store:
                proposal_store.scan()
            with index.lock:
                synced = index.sync()
                prepared = vectors.vectorize()
            return {
                "documents": synced.added + synced.modified + synced.unchanged,
                "chunks": prepared.chunks,
            }
        except (IngestionError, RetrievalError, GuideError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/drafts", response_model=list[Draft])
    def list_drafts():
        return draft_store.list()

    @app.get("/api/v1/drafts/{draft_id}", response_model=Draft)
    def get_draft(draft_id: str):
        try:
            return draft_store.get(draft_id)
        except DraftError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/drafts", response_model=Draft, status_code=201)
    def save_draft(data: ServiceForm):
        try:
            return draft_store.save(data)
        except DraftError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/api/v1/drafts/{draft_id}", response_model=Draft)
    def update_draft(draft_id: str, data: DraftUpdate):
        try:
            return draft_store.save(data.data, draft_id, data.revision)
        except DraftError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/documentation/organize")
    def organize_notes(data: NotesRequest):
        try:
            form = notes_organizer.organize(data.notes)
            return {"data": form, "questions": missing_questions(form)}
        except DraftError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def local_guide():
        if proposal_store is None:
            raise HTTPException(
                status_code=409, detail="Esta acción requiere la guía local administrada."
            )
        return proposal_store

    @app.exception_handler(GuideError)
    async def guide_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/api/v1/guide/status")
    def guide_status():
        snapshot = read_snapshot(configured_repo, configured_ref)
        return {
            "mode": mode,
            "managed": workspace is not None,
            "documents": len(snapshot.documents),
            "text_bytes": sum(len(doc.content.encode()) for doc in snapshot.documents),
            "pending": len(proposal_store.list()) if proposal_store else 0,
            "auto_refresh": enabled_refresh,
            **refresh_state,
        }

    @app.get("/api/v1/guide/proposals")
    def list_proposals():
        return local_guide().list()

    @app.get("/api/v1/guide/proposals/{proposal_id}")
    def proposal_detail(proposal_id: str):
        store = local_guide()
        row = next((item for item in store.list(full=True) if item["id"] == proposal_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada.")
        row["previous_content"] = next(
            (doc.content for doc in workspace.snapshot().documents if doc.path == row["path"]), ""
        )
        return row

    @app.post("/api/v1/guide/proposals/{proposal_id}/approve")
    def approve_proposal(
        proposal_id: str, confirmation: ReviewConfirmation, request: Request,
    ):
        if not confirmation.reviewed:
            raise HTTPException(status_code=422, detail="Revisa el documento antes de aprobarlo.")
        store = local_guide()
        row = next((row for row in store.list() if row["id"] == proposal_id), None)
        if row and row["deletion"]:
            if len(confirmation.reason.strip()) < 10:
                raise HTTPException(422, "Explica el motivo de eliminación (mínimo 10 caracteres).")
            if confirmation.confirmation_text.strip().upper() != "ELIMINAR":
                raise HTTPException(422, "Escribe ELIMINAR para confirmar la retirada.")
            validate_content(confirmation.reason)
        commit = store.approve(proposal_id, reason=confirmation.reason.strip())
        refresh()
        return {"commit": commit, "index_error": refresh_state["last_error"]}

    @app.post("/api/v1/guide/proposals/{proposal_id}/reject")
    def reject_proposal(proposal_id: str, request: Request):
        local_guide().reject(proposal_id)
        return {"rejected": True}

    @app.post("/api/v1/guide/edit")
    def edit_document(data: DocumentEdit):
        store = local_guide()
        validate_content(data.content)
        with workspace.lock, index.lock:
            current = next((doc for doc in workspace.snapshot().documents
                            if doc.path == data.path), None)
            if current is None:
                raise HTTPException(404, "Documento no encontrado.")
            if digest(current.content) != data.base_sha256:
                raise HTTPException(409, "El documento cambió. Ábrelo de nuevo antes de editar.")
            return {"created": store.stage_many(
                [(data.path, data.content)], "Edición desde la biblioteca",
            )}

    @app.post("/api/v1/guide/delete")
    def delete_document(data: DocumentDelete):
        store = local_guide()
        with workspace.lock, index.lock:
            current = next((doc for doc in workspace.snapshot().documents
                            if doc.path == data.path), None)
            if current is None:
                raise HTTPException(404, "Documento no encontrado.")
            if digest(current.content) != data.base_sha256:
                raise HTTPException(409, "El documento cambió. Ábrelo de nuevo antes de eliminar.")
            created = store.stage_many(
                [(data.path, None)], "Solicitud de eliminación", allow_retry=True,
            )
            proposal = next((row for row in store.list()
                             if row["path"] == data.path and row["deletion"]), None)
        return {"created": created, "proposal": proposal}

    @app.post("/api/v1/drafts/{draft_id}/propose")
    def propose_draft(draft_id: str, data: DraftProposal):
        store = local_guide()
        try:
            draft = draft_store.get(draft_id)
        except DraftError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if draft.revision != data.revision:
            raise HTTPException(
                status_code=409, detail="Guarda y vuelve a abrir el borrador actualizado."
            )
        if draft.data.kind == "incident":
            if not (draft.data.incident_symptoms or draft.data.errors):
                raise HTTPException(422, "Describe los síntomas antes de preparar el error.")
            if draft.data.incident_status == "resolved" and not (
                draft.data.incident_solution or draft.data.procedures
            ):
                raise HTTPException(
                    422, "Indica la solución antes de marcar el error como resuelto.",
                )
        path = (
            f"projects/{slug(draft.data.project)}/{slug(draft.data.area)}/"
            f"{slug(draft.data.service or draft.data.name)}/"
            f"{slug(draft.data.kind)}/{slug(draft.data.name)}-{draft.id[:8]}.md"
        )
        return {"created": store.stage_many([(path, draft.markdown)], "Formulario revisable")}

    @app.post("/api/v1/guide/import-file")
    def import_file(data: FileImport):
        document = import_document(data.filename, data.content, data.project, data.area)
        return {"created": local_guide().stage_many([document], "Archivo local: " + data.filename)}

    @app.post("/api/v1/guide/import-package")
    def import_package(data: PackageImport):
        try:
            payload = base64.b64decode(data.payload, validate=True)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Paquete mal codificado.") from exc
        return {"created": local_guide().import_package(payload)}

    @app.get("/api/v1/guide/export")
    def export_guide():
        local_guide()
        return Response(
            workspace.export(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="Mi-guia-support-ai.zip"',
            },
        )

    @app.get("/api/v1/guide/application")
    def export_application():
        local_guide()
        root = Path(__file__).resolve().parents[2]
        return Response(
            application_package(root, workspace),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="SupportAI-portable.zip"',
            },
        )

    return app


app = create_app()
