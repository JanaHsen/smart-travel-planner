"""
RAG retrieval: embed query → pgvector cosine similarity search → ranked results.

The <=> operator is pgvector's cosine-distance operator (lower = more similar).
We use raw SQL via session.execute(text(...)) rather than the ORM because
SQLAlchemy has no native mapping for <=>, and wrapping it in a custom type
expression would add more complexity than a single parameterised text() call.

Cosine *similarity* is returned as score = 1 − cosine_distance so that higher
scores are better (range roughly 0.0–1.0 for normalised embeddings).
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.embeddings import EmbeddingModel

log = structlog.get_logger()


async def search_destinations(
    query: str,
    session: AsyncSession,
    embedder: EmbeddingModel,
    top_k: int = 5,
) -> list[dict]:
    """
    Embed *query* and return the *top_k* most similar chunks from destination_embeddings.

    Parameters
    ----------
    query:    Natural-language travel query (e.g. "beaches in Thailand with cheap food").
    session:  Open AsyncSession; must be connected to a DB with pgvector installed.
    embedder: Loaded EmbeddingModel (typically the process singleton).
    top_k:    Number of results to return (default 5).

    Returns
    -------
    List of dicts ordered by descending similarity, each with:
        text     – the matched chunk string
        source   – document path / URL the chunk came from
        score    – cosine similarity in [0, 1] (higher = more relevant)
        metadata – dict stored alongside the chunk at ingest time
    """
    log.debug("search_destinations_start", query=query[:80], top_k=top_k)

    vecs = await embedder.embed_batch([query])
    query_vec = vecs[0]

    # pgvector expects the vector as a bracketed comma-separated string.
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"

    sql = text(
        """
        SELECT
            chunk_text,
            document_source,
            metadata_,
            1 - (embedding <=> CAST(:embedding AS vector)) AS score
        FROM destination_embeddings
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
        """
    )

    result = await session.execute(sql, {"embedding": vec_literal, "top_k": top_k})
    rows = result.fetchall()

    hits = [
        {
            "text": row.chunk_text,
            "source": row.document_source,
            "score": float(row.score),
            "metadata": row.metadata_,
        }
        for row in rows
    ]

    log.debug("search_destinations_done", hits=len(hits), top_score=hits[0]["score"] if hits else None)
    return hits
