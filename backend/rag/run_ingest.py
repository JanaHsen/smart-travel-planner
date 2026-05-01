"""
CLI entry point for the RAG document ingestion pipeline.

Usage (run from the backend/ directory so that app.* imports resolve):

    python -m rag.run_ingest

The script loads the embedding model once, opens a single async database session,
and delegates to ingest_all(). Structured logs are written to stdout. Exit code is
non-zero on unhandled exceptions.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import structlog

from app.db.session import AsyncSessionLocal
from app.utils.logging import configure_logging
from rag.embeddings import EmbeddingModel
from rag.ingest import ingest_all


async def _run() -> None:
    configure_logging(logging.INFO)
    log = structlog.get_logger()
    log.info("run_ingest_started")

    embedder = EmbeddingModel.get()

    async with AsyncSessionLocal() as session:
        await ingest_all(session, embedder)

    log.info("run_ingest_finished")


def main() -> None:
    try:
        asyncio.run(_run())
    except Exception:
        structlog.get_logger().exception("run_ingest_failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
