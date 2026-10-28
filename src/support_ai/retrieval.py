"""Immutable Qdrant generations with an atomic SQL publication pointer."""

import math
import re
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, insert, select

from support_ai.chunking import Chunk
from support_ai.embeddings import Embedder, EmbeddingError, LocalEmbedder, validate_vectors
from support_ai.ingestion import KnowledgeIndex
from support_ai.storage import embedding_cache, vector_states


class RetrievalError(ValueError):
    pass


class VectorStatus(BaseModel):
    indexed_commit: str | None = None
    source_commit: str | None = None
    model_signature: str | None = None
    chunks: int = 0
    stale: bool = True


class VectorizeResult(BaseModel):
    commit: str
    chunks: int
    embeddings_created: int
    embeddings_reused: int


class SearchHit(BaseModel):
    score: float
    source: Chunk


class SearchResult(BaseModel):
    indexed_commit: str
    source_commit: str | None
    stale: bool
    hits: list[SearchHit]


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
    top_k: int = Field(default=3, ge=1, le=10)


class SemanticIndex:
    def __init__(
        self, index: KnowledgeIndex, path: Path, model_path: Path, embedder: Embedder | None = None,
    ):
        self.index, self.path = index, path
        self.embedder = embedder or LocalEmbedder(model_path)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(
                path=str(self.path), force_disable_check_same_thread=True,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _state(self) -> dict | None:
        with self.index.engine.connect() as connection:
            row = connection.execute(select(vector_states).where(
                vector_states.c.repository_id == self.index.repository_id,
            )).mappings().first()
            return dict(row) if row else None

    def status(self) -> VectorStatus:
        with self.index.lock:
            state = self._state()
            source_commit = self.index.status().indexed_commit
            if state is None:
                return VectorStatus(source_commit=source_commit)
            return VectorStatus(
                indexed_commit=state["indexed_commit"], source_commit=source_commit,
                model_signature=state["model_signature"], chunks=state["chunk_count"],
                stale=state["indexed_commit"] != source_commit,
            )

    def vectorize(self) -> VectorizeResult:
        with self.index.lock:
            collection = None
            published = False
            try:
                from qdrant_client import models

                status = self.index.status()
                if status.indexed_commit is None:
                    raise RetrievalError("Sincroniza primero el repositorio con /knowledge/sync.")
                source = self.index.list_chunks(limit=status.chunks)
                signature = self.embedder.signature
                old = self._state()
                if (old and old["indexed_commit"] == source.indexed_commit
                        and old["model_signature"] == signature
                        and self.client.collection_exists(old["collection"])
                        and self.client.count(old["collection"]).count == len(source.items)):
                    return VectorizeResult(
                        commit=source.indexed_commit, chunks=len(source.items),
                        embeddings_created=0, embeddings_reused=len(source.items),
                    )
                with self.index.engine.connect() as connection:
                    cache = dict(connection.execute(select(
                        embedding_cache.c.chunk_id, embedding_cache.c.vector,
                    ).where(
                        embedding_cache.c.repository_id == self.index.repository_id,
                        embedding_cache.c.model_signature == signature,
                    )).tuples().all())
                pending = [piece for piece in source.items if piece.id not in cache]
                for offset in range(0, len(pending), 8):
                    batch = pending[offset:offset + 8]
                    vectors = self.embedder.encode([piece.content for piece in batch])
                    validate_vectors(vectors, len(batch))
                    cache.update(zip((piece.id for piece in batch), vectors, strict=True))
                # Empty repositories still need a correctly dimensioned collection.
                dimension_vectors = ([cache[piece.id] for piece in source.items] if source.items
                                     else self.embedder.encode(["dimension"], query=True))
                dimension = validate_vectors(dimension_vectors, len(dimension_vectors))
                collection = f"support_ai_{self.index.repository_id[:16]}_{uuid.uuid4().hex}"
                self.client.create_collection(
                    collection, vectors_config=models.VectorParams(
                        size=dimension, distance=models.Distance.COSINE,
                    ),
                )
                for offset in range(0, len(source.items), 64):
                    self.client.upsert(collection, points=[
                        models.PointStruct(
                            id=str(uuid.uuid5(uuid.NAMESPACE_URL,
                                             self.index.repository_id + ":" + piece.id)),
                            vector=cache[piece.id], payload={
                                "repository_id": self.index.repository_id, **piece.model_dump(),
                            },
                        ) for piece in source.items[offset:offset + 64]
                    ], wait=True)
                if self.client.count(collection).count != len(source.items):
                    raise RetrievalError("La generación vectorial quedó incompleta.")
                # Qdrant is complete before publishing. A failure keeps the old pointer valid.
                with self.index.engine.begin() as connection:
                    connection.execute(delete(vector_states).where(
                        vector_states.c.repository_id == self.index.repository_id,
                    ))
                    connection.execute(insert(vector_states).values(
                        repository_id=self.index.repository_id, collection=collection,
                        indexed_commit=source.indexed_commit, model_signature=signature,
                        chunk_count=len(source.items),
                    ))
                    connection.execute(delete(embedding_cache).where(
                        embedding_cache.c.repository_id == self.index.repository_id,
                    ))
                    if source.items:
                        connection.execute(insert(embedding_cache), [
                            {"repository_id": self.index.repository_id,
                             "model_signature": signature, "chunk_id": piece.id,
                             "vector": cache[piece.id]} for piece in source.items
                        ])
                published = True
                if old:
                    try:
                        self.client.delete_collection(old["collection"])
                    except Exception:
                        pass  # Published generation is valid; cleanup can be retried separately.
                return VectorizeResult(
                    commit=source.indexed_commit, chunks=len(source.items),
                    embeddings_created=len(pending),
                    embeddings_reused=len(source.items) - len(pending),
                )
            except Exception as exc:
                if collection and not published:
                    try:
                        self.client.delete_collection(collection)
                    except Exception:
                        pass
                if isinstance(exc, RetrievalError):
                    raise
                message = (str(exc) if isinstance(exc, EmbeddingError)
                           else "No se pudo preparar el índice vectorial local.")
                raise RetrievalError(message) from exc

    def search(self, query: str, top_k: int = 3) -> SearchResult:
        with self.index.lock:
            try:
                from qdrant_client import models

                state = self._state()
                if state is None:
                    raise RetrievalError("Prepara primero los vectores con /knowledge/vectorize.")
                if self.embedder.signature != state["model_signature"]:
                    raise RetrievalError("El modelo cambió; vuelve a preparar el índice vectorial.")
                vector = self.embedder.encode([query.strip()], query=True)
                validate_vectors(vector, 1)
                points = self.client.query_points(
                    state["collection"], query=vector[0], limit=top_k,
                    query_filter=models.Filter(must=[models.FieldCondition(
                        key="repository_id",
                        match=models.MatchValue(value=self.index.repository_id),
                    )]),
                ).points
                hits = []
                for point in points:
                    payload = point.payload or {}
                    if (payload.get("repository_id") != self.index.repository_id
                            or payload.get("commit") != state["indexed_commit"]):
                        raise RetrievalError("Las fuentes no corresponden a la generación activa.")
                    hits.append(SearchHit(score=point.score, source=Chunk(**payload)))
                current = self.index.status().indexed_commit
                return SearchResult(
                    indexed_commit=state["indexed_commit"], source_commit=current,
                    stale=current != state["indexed_commit"], hits=hits,
                )
            except Exception as exc:
                if isinstance(exc, RetrievalError):
                    raise
                message = (str(exc) if isinstance(exc, EmbeddingError)
                           else "Búsqueda vectorial local no disponible.")
                raise RetrievalError(message) from exc

    def hybrid_search(self, query: str, top_k: int = 4) -> SearchResult:
        """Fuse cosine and lexical BM25 ranks over the same immutable generation."""
        with self.index.lock:
            semantic = self.search(query, top_k=12)
            try:
                from qdrant_client import models

                state = self._state()
                all_sources = {}
                offset = None
                while True:
                    points, offset = self.client.scroll(
                        state["collection"], limit=256, offset=offset, with_vectors=False,
                        scroll_filter=models.Filter(must=[models.FieldCondition(
                            key="repository_id",
                            match=models.MatchValue(value=self.index.repository_id),
                        )]),
                    )
                    for point in points:
                        piece = Chunk(**point.payload)
                        if piece.commit != semantic.indexed_commit:
                            raise RetrievalError("La generación de fuentes es inconsistente.")
                        all_sources[piece.id] = piece
                    if offset is None:
                        break
                def tokens(text):
                    normalized = unicodedata.normalize("NFKD", text.lower())
                    return re.findall(r"[a-z0-9_/-]+", "".join(
                        char for char in normalized if not unicodedata.combining(char)
                    ))

                corpus = {key: Counter(tokens(piece.path + " " + piece.content))
                          for key, piece in all_sources.items()}
                lengths = {key: sum(terms.values()) for key, terms in corpus.items()}
                average = sum(lengths.values()) / max(1, len(corpus))
                lexical = Counter()
                for term in set(tokens(query)):
                    frequency = sum(term in terms for terms in corpus.values())
                    idf = math.log(1 + (len(corpus) - frequency + 0.5) / (frequency + 0.5))
                    for key, terms in corpus.items():
                        tf = terms[term]
                        if tf:
                            lexical[key] += idf * tf * 2.2 / (
                                tf + 1.2 * (0.25 + 0.75 * lengths[key] / max(1, average))
                            )
                fused = Counter()
                rankings = [[hit.source.id for hit in semantic.hits],
                            [key for key, _ in lexical.most_common(12)]]
                for ranking in rankings:
                    for rank, key in enumerate(ranking, 1):
                        fused[key] += 1 / (60 + rank)
                return semantic.model_copy(update={"hits": [
                    SearchHit(score=score, source=all_sources[key])
                    for key, score in fused.most_common(top_k)
                ]})
            except RetrievalError:
                raise
            except Exception as exc:
                raise RetrievalError("Búsqueda híbrida local no disponible.") from exc
