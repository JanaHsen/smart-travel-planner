from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rag import search_destinations
from rag.embeddings import EmbeddingModel

log = structlog.get_logger()


class RagSearchInput(BaseModel):
    query: str = Field(..., description="Travel destination search query")
    top_k: int = Field(default=5, ge=1, le=10)


class RagResult(BaseModel):
    text: str
    source: str
    score: float
    metadata: dict[str, Any]


class RagSearchOutput(BaseModel):
    results: list[RagResult]
    query: str


class ToolError(BaseModel):
    error: str
    retryable: bool


async def rag_search(
    inp: RagSearchInput,
    *,
    session: AsyncSession,
    embedder: EmbeddingModel,
) -> RagSearchOutput | ToolError:
    t0 = time.perf_counter()
    try:
        raw = await search_destinations(inp.query, session, embedder, top_k=inp.top_k)
        results = [
            RagResult(
                text=r["text"],
                source=r["source"],
                score=r["score"],
                metadata=r.get("metadata") or {},
            )
            for r in raw
        ]
        duration_ms = int((time.perf_counter() - t0) * 1000)
        log.info("tool.rag_search", query=inp.query[:60], results=len(results), duration_ms=duration_ms)
        return RagSearchOutput(results=results, query=inp.query)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        log.error("tool.rag_search.error", error=str(exc), duration_ms=duration_ms)
        return ToolError(error=str(exc), retryable=True)
