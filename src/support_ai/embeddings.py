"""Explicit download command and strictly local CPU embedding provider."""

import argparse
import hashlib
import json
import math
import os
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

MODEL_ID = "intfloat/multilingual-e5-small"
MANIFEST = "support-ai-model.json"
MODEL_FILES = [
    "config.json", "config_sentence_transformers.json", "sentence_bert_config.json",
    "modules.json", "1_Pooling/config.json", "model.safetensors", "tokenizer.json",
    "tokenizer_config.json", "special_tokens_map.json", "sentencepiece.bpe.model",
]


class EmbeddingError(ValueError):
    pass


class Embedder(Protocol):
    @property
    def signature(self) -> str: ...

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


def validate_vectors(vectors: list[list[float]], count: int) -> int:
    if len(vectors) != count or not vectors:
        raise EmbeddingError("El proveedor devolvió una cantidad inválida de embeddings.")
    dimension = len(vectors[0])
    if not dimension or any(
        len(vector) != dimension or not all(math.isfinite(value) for value in vector)
        or sum(value * value for value in vector) <= 0 for vector in vectors
    ):
        raise EmbeddingError("El proveedor devolvió embeddings inválidos.")
    return dimension


class LocalEmbedder:
    def __init__(self, path: Path):
        self.path = path
        self._model = None
        self._signature: str | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            manifest = json.loads((self.path / MANIFEST).read_text(encoding="utf-8"))
            if manifest["model_id"] != MODEL_ID or not manifest["files"]:
                raise ValueError("Unexpected model")
            for name, expected in manifest["files"].items():
                if name not in MODEL_FILES:
                    raise ValueError("Unexpected model file")
                actual = hashlib.sha256((self.path / name).read_bytes()).hexdigest()
                if actual != expected:
                    raise ValueError("Model checksum mismatch")
            # Set before importing the ML libraries. Only the download CLI uses the network.
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            import torch
            from sentence_transformers import SentenceTransformer

            torch.set_num_threads(min(8, os.cpu_count() or 1))
            model = SentenceTransformer(
                str(self.path.resolve()), device="cpu", local_files_only=True,
                trust_remote_code=False, model_kwargs={"use_safetensors": True},
            )
            self._signature = hashlib.sha256(json.dumps({
                "manifest": manifest, "prefixes": ["query: ", "passage: "],
                "normalize": True, "max_tokens": 512, "provider": "e5-cpu-v1",
                "versions": {name: version(name) for name in (
                    "torch", "sentence-transformers", "transformers",
                )},
            }, sort_keys=True).encode()).hexdigest()
            self._model = model
        except Exception as exc:
            raise EmbeddingError(
                "Modelo local no disponible o inválido. Ejecuta python -m support_ai.embeddings.",
            ) from exc

    @property
    def signature(self) -> str:
        self._load()
        assert self._signature is not None
        return self._signature

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        self._load()
        if not texts:
            return []
        prefixed = [("query: " if query else "passage: ") + text for text in texts]
        try:
            lengths = self._model.tokenizer(
                prefixed, truncation=False, padding=False, return_length=True,
            )["length"]
            if any(length > min(512, self._model.max_seq_length) for length in lengths):
                raise EmbeddingError(
                    "Un texto supera el límite de tokens del modelo; reduce su tamaño.",
                )
            vectors = self._model.encode(
                prefixed, batch_size=8, normalize_embeddings=True, show_progress_bar=False,
                prompt="",
            ).tolist()
            validate_vectors(vectors, len(texts))
            return vectors
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError("No se pudieron generar los embeddings locales.") from exc


def prepare_model(path: Path, revision: str | None = None) -> None:
    """Network-enabled installation step, never invoked from an HTTP request."""
    from huggingface_hub import HfApi, snapshot_download

    if revision is None and (path / MANIFEST).is_file():
        revision = json.loads((path / MANIFEST).read_text(encoding="utf-8"))["revision"]
    revision = HfApi().model_info(MODEL_ID, revision=revision).sha
    snapshot_download(
        MODEL_ID, revision=revision, local_dir=path, allow_patterns=MODEL_FILES,
    )
    files = {name: hashlib.sha256((path / name).read_bytes()).hexdigest()
             for name in MODEL_FILES if (path / name).is_file()}
    if "model.safetensors" not in files:
        raise EmbeddingError("La descarga no contiene pesos safetensors.")
    (path / MANIFEST).write_text(json.dumps({
        "model_id": MODEL_ID, "revision": revision, "files": files,
    }, indent=2), encoding="utf-8")
    print(f"Modelo preparado en {path}; revisión {revision}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descargar embeddings para uso offline")
    parser.add_argument("--path", type=Path, default=Path("data/models/multilingual-e5-small"))
    parser.add_argument("--revision", help="Revisión explícita; por defecto conserva la existente")
    args = parser.parse_args()
    prepare_model(args.path, args.revision)
