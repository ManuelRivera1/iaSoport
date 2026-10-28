"""Incremental, atomic indexing for one configured local Git source."""

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from support_ai.chunking import CHUNKER_VERSION, Chunk, chunk_document
from support_ai.git_reader import RepositoryError, read_snapshot
from support_ai.storage import chunks, documents, open_database, repositories

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[\"']?"
               r"[^\s\"'<>`]{8,}"),
)


class IngestionError(ValueError):
    """Safe error message suitable for the local API."""


class IndexStatus(BaseModel):
    indexed_commit: str | None = None
    documents: int = 0
    chunks: int = 0
    last_success_at: str | None = None
    last_error: str | None = None


class SyncResult(BaseModel):
    commit: str
    added: int
    modified: int
    deleted: int
    unchanged: int
    chunks_created: int


class IndexedChunks(BaseModel):
    indexed_commit: str | None
    total: int
    items: list[Chunk]


class KnowledgeIndex:
    def __init__(self, repo: Path, ref: str, database: Path):
        self.repo, self.ref, self.database = repo, ref, database
        identity = f"{repo.resolve()}\0{ref}"
        self.repository_id = hashlib.sha256(identity.encode()).hexdigest()
        self.lock = RLock()
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        # Callers hold the lock; health checks never create files or tables.
        if self._engine is None:
            self._engine = open_database(self.database)
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()

    def _ensure_repository(self) -> None:
        with self.engine.begin() as connection:
            if not connection.scalar(select(repositories.c.id).where(
                repositories.c.id == self.repository_id,
            )):
                connection.execute(insert(repositories).values(
                    id=self.repository_id, chunker_version=CHUNKER_VERSION,
                ))

    def sync(self) -> SyncResult:
        with self.lock:
            try:
                self._ensure_repository()
                return self._sync()
            except (RepositoryError, IngestionError, SQLAlchemyError, OSError) as exc:
                message = (str(exc) if isinstance(exc, (RepositoryError, IngestionError))
                           else "No se pudo guardar el índice local.")
                try:
                    with self.engine.begin() as connection:
                        connection.execute(update(repositories).where(
                            repositories.c.id == self.repository_id,
                        ).values(last_error=message))
                except (SQLAlchemyError, OSError):
                    pass
                raise IngestionError(message) from exc

    def _sync(self) -> SyncResult:
        snapshot = read_snapshot(self.repo, self.ref)
        source = {doc.path: doc for doc in snapshot.documents}
        with self.engine.begin() as connection:
            state = connection.execute(select(repositories).where(
                repositories.c.id == self.repository_id,
            )).mappings().one()
            old = dict(connection.execute(select(documents.c.path, documents.c.sha256).where(
                documents.c.repository_id == self.repository_id,
            )).tuples().all())
            added = source.keys() - old.keys()
            removed = old.keys() - source.keys()
            changed = {path for path in source.keys() & old.keys()
                       if source[path].sha256 != old[path]
                       or state["chunker_version"] != CHUNKER_VERSION}
            replacement = added | changed
            count = 0
            for path in sorted(removed | replacement):
                connection.execute(delete(chunks).where(
                    chunks.c.repository_id == self.repository_id, chunks.c.path == path,
                ))
                connection.execute(delete(documents).where(
                    documents.c.repository_id == self.repository_id, documents.c.path == path,
                ))
                if path not in replacement:
                    continue
                document = source[path]
                if any(pattern.search(document.content) for pattern in SECRET_PATTERNS):
                    raise IngestionError(
                        "Posible secreto detectado; revisa la documentación de origen.",
                    )
                pieces = chunk_document(document)
                connection.execute(insert(documents).values(
                    repository_id=self.repository_id, path=path, sha256=document.sha256,
                ))
                if pieces:
                    connection.execute(insert(chunks), [
                        {"repository_id": self.repository_id,
                         **piece.model_dump(exclude={"commit"})} for piece in pieces
                    ])
                count += len(pieces)
            connection.execute(update(repositories).where(
                repositories.c.id == self.repository_id,
            ).values(indexed_commit=snapshot.commit, chunker_version=CHUNKER_VERSION,
                     last_success_at=datetime.now(UTC).isoformat(), last_error=None))
        return SyncResult(
            commit=snapshot.commit, added=len(added), modified=len(changed), deleted=len(removed),
            unchanged=len(source) - len(replacement), chunks_created=count,
        )

    def status(self) -> IndexStatus:
        with self.lock, self.engine.connect() as connection:
            state = connection.execute(select(repositories).where(
                repositories.c.id == self.repository_id,
            )).mappings().first()
            if state is None:
                return IndexStatus()
            counts = [connection.scalar(select(func.count()).select_from(table).where(
                table.c.repository_id == self.repository_id,
            )) for table in (documents, chunks)]
            return IndexStatus(
                indexed_commit=state["indexed_commit"], documents=counts[0], chunks=counts[1],
                last_success_at=state["last_success_at"], last_error=state["last_error"],
            )

    def list_chunks(self, offset: int = 0, limit: int = 50) -> IndexedChunks:
        with self.lock, self.engine.connect() as connection:
            commit = connection.scalar(select(repositories.c.indexed_commit).where(
                repositories.c.id == self.repository_id,
            ))
            total = connection.scalar(select(func.count()).select_from(chunks).where(
                chunks.c.repository_id == self.repository_id,
            ))
            rows = connection.execute(select(chunks).where(
                chunks.c.repository_id == self.repository_id,
            ).order_by(chunks.c.path, chunks.c.ordinal).offset(offset).limit(limit)).mappings()
            return IndexedChunks(indexed_commit=commit, total=total, items=[
                Chunk(**{k: v for k, v in row.items() if k != "repository_id"}, commit=commit)
                for row in rows
            ])
