"""
Embedding model wrapper — loaded once as a process-level singleton.

sentence-transformers' encode() is CPU-bound (no GIL release during the heavy
matrix math). We push every call into a thread-pool worker via asyncio.to_thread()
so the event loop stays responsive while embeddings are computed, allowing other
coroutines (DB queries, HTTP handlers) to make progress concurrently.

Texts are processed in sub-batches of 64 to keep per-call memory predictable;
the model itself handles internal micro-batching. 64 is a safe default that keeps
RAM usage under ~500 MB even for large documents.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

import structlog
from sentence_transformers import SentenceTransformer

log = structlog.get_logger()

_BATCH_SIZE = 64
_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingModel:
    """
    Async wrapper around a sentence-transformers model.

    Use ``EmbeddingModel.get()`` to obtain the singleton rather than
    instantiating directly, so the model is loaded only once per process.
    """

    _instance: ClassVar["EmbeddingModel | None"] = None

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        log.info("loading_embedding_model", model=model_name)
        self._model = SentenceTransformer(model_name)
        dim = self._model.get_sentence_embedding_dimension()
        log.info("embedding_model_ready", model=model_name, dimensions=dim)

    @classmethod
    def get(cls, model_name: str = _DEFAULT_MODEL) -> "EmbeddingModel":
        """Return the process-level singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed *texts*, returning one 384-dim vector per input string.

        Processing is split into sub-batches of ``_BATCH_SIZE`` texts.
        Each sub-batch is dispatched to a thread pool via asyncio.to_thread()
        so the event loop is never blocked.

        Parameters
        ----------
        texts: One or more strings to embed.

        Returns
        -------
        List of float lists, same length and order as *texts*.
        """
        results: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            sub = texts[i : i + _BATCH_SIZE]
            vecs = await asyncio.to_thread(
                self._model.encode,
                sub,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            results.extend(v.tolist() for v in vecs)
        return results
