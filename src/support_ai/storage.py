"""Local transactional index. One application process, no remote service required."""

from pathlib import Path

from sqlalchemy import JSON, Column, Index, Integer, MetaData, String, Table, Text, create_engine
from sqlalchemy.engine import Engine

metadata = MetaData()

catalogs = Table(
    "catalogs", metadata,
    Column("id", String(32), primary_key=True),
    Column("repository_id", String(64), nullable=False, index=True),
    Column("category", String(20), nullable=False),
    Column("name", String(120), nullable=False),
    Column("project_id", String(32), nullable=True),
    Column("active", Integer, nullable=False, default=1),
    Column("revision", Integer, nullable=False, default=1),
)

repositories = Table(
    "repositories", metadata,
    Column("id", String(64), primary_key=True),
    Column("indexed_commit", String(64), nullable=True),
    Column("chunker_version", String(64), nullable=False),
    Column("last_success_at", String(40), nullable=True),
    Column("last_error", Text, nullable=True),
)
documents = Table(
    "documents", metadata,
    Column("repository_id", String(64), primary_key=True),
    Column("path", Text, primary_key=True),
    Column("sha256", String(64), nullable=False),
)
chunks = Table(
    "chunks", metadata,
    Column("repository_id", String(64), primary_key=True),
    Column("id", String(64), primary_key=True),
    Column("path", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("start_line", Integer, nullable=False),
    Column("end_line", Integer, nullable=False),
    Column("content", Text, nullable=False),
)
Index("ix_chunks_repository_path_ordinal", chunks.c.repository_id, chunks.c.path, chunks.c.ordinal,
      unique=True)

vector_states = Table(
    "vector_states", metadata,
    Column("repository_id", String(64), primary_key=True),
    Column("collection", String(160), nullable=False),
    Column("indexed_commit", String(64), nullable=False),
    Column("model_signature", String(64), nullable=False),
    Column("chunk_count", Integer, nullable=False),
)
embedding_cache = Table(
    "embedding_cache", metadata,
    Column("repository_id", String(64), primary_key=True),
    Column("model_signature", String(64), primary_key=True),
    Column("chunk_id", String(64), primary_key=True),
    Column("vector", JSON, nullable=False),
)
drafts = Table(
    "drafts", metadata,
    Column("id", String(32), primary_key=True),
    Column("repository_id", String(64), nullable=False, index=True),
    Column("revision", Integer, nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("data", JSON, nullable=False),
)
proposals = Table(
    "proposals", metadata,
    Column("id", String(32), primary_key=True),
    Column("repository_id", String(64), nullable=False, index=True),
    Column("path", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("base_sha256", String(64), nullable=True),
    Column("origin", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", String(40), nullable=False),
)


def open_database(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Explicit modern transaction mode is supported by Python >= 3.12.
    engine = create_engine(
        "sqlite+pysqlite:///" + path.resolve().as_posix(),
        connect_args={"check_same_thread": False, "autocommit": False, "timeout": 20},
    )
    metadata.create_all(engine)
    return engine
