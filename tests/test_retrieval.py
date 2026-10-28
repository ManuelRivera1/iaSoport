import math
from unittest.mock import patch

import pytest
from conftest import run
from fastapi.testclient import TestClient

from support_ai.embeddings import EmbeddingError, LocalEmbedder, validate_vectors
from support_ai.ingestion import KnowledgeIndex
from support_ai.main import create_app
from support_ai.retrieval import RetrievalError, SemanticIndex

pytest.importorskip("qdrant_client")


class TestEmbedder:
    """Deterministic test double, never used by the running application."""

    __test__ = False
    signature = "test-v1"

    def __init__(self):
        self.passages = 0

    def encode(self, texts, *, query=False):
        if not query:
            self.passages += len(texts)
        return [[1.0, float("demo" in text), float("payment" in text)] for text in texts]


@pytest.fixture
def semantic(repo, tmp_path):
    index = KnowledgeIndex(repo, "main", tmp_path / "index.db")
    index.sync()
    vectors = SemanticIndex(index, tmp_path / "qdrant", tmp_path / "unused", TestEmbedder())
    yield vectors
    vectors.close()
    index.close()


def commit(repo):
    run(repo, "add", "-A")
    run(repo, "-c", "core.hooksPath=", "commit", "-m", "update")


def test_real_qdrant_search_and_incremental_cache(semantic, repo):
    first = semantic.vectorize()
    assert first.embeddings_created == 1
    repeated = semantic.vectorize()
    assert repeated.embeddings_created == 0
    assert semantic.embedder.passages == 1
    (repo / "payment.md").write_text("# payment\nPayment diagnosis", encoding="utf-8")
    commit(repo)
    semantic.index.sync()
    assert semantic.status().stale
    old = semantic.search("GET demo")
    assert old.stale and old.hits[0].source.commit == first.commit
    added = semantic.vectorize()
    assert added.embeddings_created == added.embeddings_reused == 1
    assert semantic.embedder.passages == 2
    found = semantic.search("GET demo")
    assert not found.stale
    assert found.hits[0].source.path == "service.md"
    assert found.hits[0].source.commit == added.commit
    assert found.hits[0].source.start_line == 1


def test_failed_publication_preserves_previous_search(semantic, repo):
    previous = semantic.vectorize()
    (repo / "new.md").write_text("# New\nNew document", encoding="utf-8")
    commit(repo)
    semantic.index.sync()
    with patch.object(semantic.client, "upsert", side_effect=RuntimeError("test failure")):
        with pytest.raises(RetrievalError):
            semantic.vectorize()
    result = semantic.search("GET demo")
    assert result.indexed_commit == previous.commit
    assert len(result.hits) == 1
    assert semantic.status().stale
    assert len(semantic.client.get_collections().collections) == 1


def test_deletion_and_empty_generation(semantic, repo):
    semantic.vectorize()
    (repo / "service.md").unlink()
    commit(repo)
    semantic.index.sync()
    result = semantic.vectorize()
    assert result.chunks == 0
    assert semantic.search("anything").hits == []
    assert len(semantic.client.get_collections().collections) == 1


def test_model_change_forces_rebuild(semantic):
    semantic.vectorize()
    semantic.embedder.signature = "test-v2"
    with pytest.raises(RetrievalError, match="modelo cambió"):
        semantic.search("GET demo")
    assert semantic.vectorize().embeddings_created == 1


def test_filter_never_returns_foreign_repository(semantic):
    from qdrant_client import models

    semantic.vectorize()
    collection = semantic._state()["collection"]
    semantic.client.upsert(collection, points=[models.PointStruct(
        id=1, vector=[1.0, 1.0, 0.0],
        payload={"repository_id": "other-company", "content": "private"},
    )])
    results = semantic.search("GET demo", top_k=10)
    assert len(results.hits) == 1
    assert results.hits[0].source.path == "service.md"


def test_qdrant_persists_after_restart(semantic):
    semantic.vectorize()
    expected = semantic.search("GET demo")
    semantic.close()
    actual = semantic.search("GET demo")
    assert actual.indexed_commit == expected.indexed_commit
    assert actual.source_commit == expected.source_commit
    assert actual.stale == expected.stale
    assert [hit.source for hit in actual.hits] == [hit.source for hit in expected.hits]
    # Qdrant persists float32 vectors; normalization can round the score on reload.
    assert [hit.score for hit in actual.hits] == pytest.approx(
        [hit.score for hit in expected.hits], rel=1e-6,
    )


def test_missing_collection_rebuilds_from_cached_embeddings(semantic):
    semantic.vectorize()
    semantic.client.delete_collection(semantic._state()["collection"])
    result = semantic.vectorize()
    assert result.embeddings_created == 0
    assert result.embeddings_reused == 1
    assert len(semantic.search("GET demo").hits) == 1


def test_missing_model_fails_locally(tmp_path):
    provider = LocalEmbedder(tmp_path / "missing")
    with pytest.raises(EmbeddingError, match="Modelo local"):
        provider.encode(["test"])


@pytest.mark.parametrize("vectors", [[[math.nan]], [[0.0]], [[1.0], [1.0, 2.0]], []])
def test_invalid_embeddings_rejected(vectors):
    with pytest.raises(EmbeddingError):
        validate_vectors(vectors, len(vectors))


def test_search_api_validation_and_workflow(repo, tmp_path):
    with TestClient(create_app(
        repo, "main", tmp_path / "index.db", vector_path=tmp_path / "qdrant",
        embedder=TestEmbedder(),
    )) as client:
        assert client.post("/api/v1/search", json={"query": "  "}).status_code == 422
        assert client.post("/api/v1/search", json={"query": "demo"}).status_code == 503
        assert client.post("/api/v1/knowledge/vectorize").status_code == 503
        client.post("/api/v1/knowledge/sync").raise_for_status()
        client.post("/api/v1/knowledge/vectorize").raise_for_status()
        result = client.post("/api/v1/search", json={"query": "GET demo", "top_k": 1})
        assert result.status_code == 200
        assert len(result.json()["hits"]) == 1
        assert not client.get("/api/v1/knowledge/vectors/status").json()["stale"]


def test_health_does_not_load_model_or_open_qdrant(tmp_path):
    path = tmp_path / "no-qdrant"
    with TestClient(create_app(vector_path=path, model_path=tmp_path / "no-model")) as client:
        assert client.get("/health/live").status_code == 200
    assert not path.exists()
