"""
Async document ingestion pipeline: read → chunk → embed → bulk-insert.

Idempotency: any document_source that already has at least one row in
destination_embeddings is skipped entirely. Safe to re-run after adding new
files; existing rows are never modified or deleted.

Bulk-insert cadence: rows accumulate in memory until _INSERT_BATCH is reached,
then they are embedded and committed together. A final forced flush handles the
tail. This avoids N round-trips to Postgres (one per chunk) while keeping memory
use bounded regardless of corpus size.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import DestinationEmbedding
from rag.chunking import chunk_document
from rag.embeddings import EmbeddingModel

log = structlog.get_logger()

_DOCUMENTS_DIR = Path(__file__).parent / "documents"
_SUPPORTED_EXTENSIONS = {".md", ".txt"}
_INSERT_BATCH = 256  # rows accumulated before a bulk embed+insert


async def _source_exists(session: AsyncSession, source: str) -> bool:
    result = await session.execute(
        select(DestinationEmbedding.id)
        .where(DestinationEmbedding.document_source == source)
        .limit(1)
    )
    return result.first() is not None


async def ingest_all(session: AsyncSession, embedder: EmbeddingModel) -> None:
    """
    Walk rag/documents/, chunk every .md/.txt file, embed, and bulk-insert.

    Parameters
    ----------
    session:  An open AsyncSession connected to the travel-planner database.
    embedder: Loaded EmbeddingModel (typically the singleton from EmbeddingModel.get()).

    Progress is emitted via structlog at INFO level for milestones and DEBUG
    level for per-document events. Errors reading individual files are logged
    as warnings and skipped rather than aborting the whole run.
    """
    files = sorted(
        p
        for p in _DOCUMENTS_DIR.rglob("*")
        if p.is_file() and p.suffix in _SUPPORTED_EXTENSIONS
    )
    backend_root = Path(__file__).parent.parent

    log.info("ingest_start", total_files=len(files), documents_dir=str(_DOCUMENTS_DIR))

    docs_processed = 0
    chunks_created = 0
    embeddings_inserted = 0

    # Pending rows waiting to be embedded and inserted.
    pending: list[dict] = []

    async def _flush(*, force: bool = False) -> None:
        nonlocal embeddings_inserted
        if not pending:
            return
        if not force and len(pending) < _INSERT_BATCH:
            return

        texts = [r["chunk_text"] for r in pending]
        vectors = await embedder.embed_batch(texts)

        rows = [
            DestinationEmbedding(
                document_source=r["document_source"],
                chunk_index=r["chunk_index"],
                chunk_text=r["chunk_text"],
                embedding=vectors[i],
                metadata_=r["metadata_"],
            )
            for i, r in enumerate(pending)
        ]
        session.add_all(rows)
        await session.commit()
        embeddings_inserted += len(rows)
        log.info("batch_inserted", rows=len(rows), total_embeddings=embeddings_inserted)
        pending.clear()

    for path in files:
        try:
            source = str(path.relative_to(backend_root))
        except ValueError:
            source = str(path)

        if await _source_exists(session, source):
            log.debug("skipping_existing_source", source=source)
            continue

        try:
            text_content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.warning("file_read_error", source=source, error=str(exc))
            continue

        chunks = chunk_document(text_content, source)
        if not chunks:
            log.debug("no_chunks_produced", source=source)
            continue

        for chunk in chunks:
            pending.append(
                {
                    "document_source": chunk["source"],
                    "chunk_index": chunk["chunk_index"],
                    "chunk_text": chunk["text"],
                    "metadata_": chunk["metadata"],
                }
            )

        docs_processed += 1
        chunks_created += len(chunks)
        log.debug("document_chunked", source=source, chunks=len(chunks))

        await _flush()

    await _flush(force=True)

    log.info(
        "ingest_complete",
        documents_processed=docs_processed,
        chunks_created=chunks_created,
        embeddings_inserted=embeddings_inserted,
    )
