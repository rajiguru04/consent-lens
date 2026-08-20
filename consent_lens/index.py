"""Retrieval: local embeddings + cosine similarity over a numpy array.

Deliberately no vector database and no RAG framework. The corpus is a few hundred
clauses; a matrix multiply is the correct tool at this size. More importantly,
every step here can be explained to a hands-on technologist without hand-waving
about what the framework is doing underneath. That is a stated requirement
(PRD NFR-1), not a preference.

Embeddings are local (sentence-transformers) so retrieval needs no API key.
Only generation calls out.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

from .chunk import Chunk

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None


def _embedder():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


class Index:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray):
        self.chunks = chunks
        self.vectors = vectors  # (n, d), L2-normalised

    @classmethod
    def build(cls) -> "Index":
        chunks = [Chunk(**c) for c in json.loads((CORPUS / "chunks.json").read_text())]
        texts = [f"{c.clause_id}\n{c.text}" for c in chunks]
        vecs = _embedder().encode(texts, normalize_embeddings=True, show_progress_bar=True)
        np.save(CORPUS / "vectors.npy", vecs)
        print(f"indexed {len(chunks)} chunks, dim={vecs.shape[1]}")
        return cls(chunks, np.asarray(vecs))

    @classmethod
    def load(cls) -> "Index":
        chunks = [Chunk(**c) for c in json.loads((CORPUS / "chunks.json").read_text())]
        return cls(chunks, np.load(CORPUS / "vectors.npy"))

    def search(self, query: str, k: int = 5, floor: float = 0.25):
        """Return [(chunk, score)] above `floor`.

        The floor matters more than k. Returning the 5 least-bad chunks for a
        question the corpus does not address is how a RAG system produces a
        confident wrong answer. Below the floor we return nothing and let the
        caller abstain.
        """
        q = _embedder().encode([query], normalize_embeddings=True)
        scores = (self.vectors @ np.asarray(q).T).ravel()
        order = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in order if scores[i] >= floor]


if __name__ == "__main__":
    Index.build()
