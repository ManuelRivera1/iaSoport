"""Small-corpus lexical retrieval: no tensor runtime or vector database required."""

import math
import re
import unicodedata
from collections import Counter

from support_ai.ingestion import KnowledgeIndex
from support_ai.retrieval import RetrievalError, SearchHit, SearchResult, VectorizeResult

STOPWORDS = set(
    "a al de del el la las los un una unos unas y o que qué como cómo cual cuál "
    "en por para con es son se me mi tu su sus hay si no lo le este esta "
    "the a an of to is how what for in on and".split()
)


def terms(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return [term for term in re.findall(r"[\w-]+", text) if term not in STOPWORDS]


class LightSearch:
    def __init__(self, index: KnowledgeIndex):
        self.index = index

    def close(self):
        pass

    def vectorize(self) -> VectorizeResult:
        status = self.index.status()
        if not status.indexed_commit:
            raise RetrievalError("Actualiza el conocimiento antes de preguntar.")
        return VectorizeResult(
            commit=status.indexed_commit,
            chunks=status.chunks,
            embeddings_created=0,
            embeddings_reused=0,
        )

    def search(self, query: str, top_k: int = 3) -> SearchResult:
        with self.index.lock:
            status = self.index.status()
            if not status.indexed_commit:
                raise RetrievalError("Pulsa Actualizar conocimiento antes de preguntar.")
            pieces = self.index.list_chunks(limit=status.chunks).items
            # Do not cut commands or silently put oversized blocks into a model context.
            pieces = [piece for piece in pieces if len(piece.content) <= 2500]
            corpus = [Counter(terms(piece.path + " " + piece.content)) for piece in pieces]
            average = sum(sum(document.values()) for document in corpus) / max(1, len(corpus))
            scores = [0.0] * len(pieces)
            for term in set(terms(query)):
                frequency = sum(term in document for document in corpus)
                idf = math.log(1 + (len(corpus) - frequency + 0.5) / (frequency + 0.5))
                for i, document in enumerate(corpus):
                    tf = document[term]
                    if tf:
                        scores[i] += (
                            idf
                            * tf
                            * 2.2
                            / (tf + 1.2 * (0.25 + 0.75 * sum(document.values()) / max(1, average)))
                        )
            ranked = sorted(range(len(pieces)), key=lambda i: (-scores[i], pieces[i].id))
            return SearchResult(
                indexed_commit=status.indexed_commit,
                source_commit=status.indexed_commit,
                stale=False,
                hits=[
                    SearchHit(score=scores[i], source=pieces[i])
                    for i in ranked[:top_k]
                    if scores[i] > 0
                ],
            )

    def hybrid_search(self, query: str, top_k: int = 4) -> SearchResult:
        return self.search(query, top_k)
