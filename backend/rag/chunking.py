"""
Document chunking for the RAG pipeline.

Chunk size rationale: 512 characters ≈ 100–150 word-piece tokens at the typical
~4 chars/token ratio for English prose, well within all-MiniLM-L6-v2's 256-token
context window. Travel documents are descriptive — 512 chars typically spans one
coherent topic segment (a neighbourhood description, a single attraction, or a
block of practical tips). Keeping chunks this small preserves retrieval precision:
returning a focused paragraph about "Montmartre nightlife" is more useful than
a 2 000-char blob that also covers museums and transport.

Overlap of 64 chars (≈12–16 tokens) carries the tail of each chunk into the next
so that sentences split at a boundary remain retrievable from either side.

Splitting priority: paragraph breaks → line breaks → sentence endings →
clause boundaries → spaces → characters. Larger semantic units are preserved
first; character-level splitting is a last-resort fallback for pathological inputs
(e.g. a single unbroken sentence longer than chunk_size).
"""

from __future__ import annotations

_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]


def _split_recursive(text: str, separators: list[str], chunk_size: int) -> list[str]:
    """Return pieces of *text*, each at most *chunk_size* chars, split hierarchically."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    sep, *rest = separators

    if sep == "":
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    raw = text.split(sep)
    # Reattach separator so rejoined chunks stay faithful to the original text.
    pieces = [p + sep for p in raw[:-1]] + ([raw[-1]] if raw[-1] else [])

    result: list[str] = []
    for piece in pieces:
        if len(piece) > chunk_size and rest:
            result.extend(_split_recursive(piece, rest, chunk_size))
        else:
            result.append(piece)
    return result


def _merge_with_overlap(pieces: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Merge fine-grained *pieces* into chunks ≤ *chunk_size* with *overlap* carry-over."""
    chunks: list[str] = []
    window: list[str] = []
    window_len = 0

    for piece in pieces:
        if not piece.strip():
            continue
        piece_len = len(piece)

        if window_len + piece_len > chunk_size and window:
            chunks.append("".join(window).strip())

            # Roll the window back: keep only the tail that fits in *overlap* chars.
            tail: list[str] = []
            tail_len = 0
            for p in reversed(window):
                if tail_len + len(p) > overlap:
                    break
                tail.insert(0, p)
                tail_len += len(p)
            window = tail
            window_len = tail_len

        window.append(piece)
        window_len += piece_len

    if window:
        last = "".join(window).strip()
        if last:
            chunks.append(last)

    return chunks


def chunk_document(
    text: str,
    source: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[dict]:
    """
    Split *text* into overlapping chunks suitable for embedding.

    Parameters
    ----------
    text:       Raw document content.
    source:     File path or URL identifying the document (stored verbatim).
    chunk_size: Maximum chunk length in characters (default 512).
    overlap:    Characters of context carried over between adjacent chunks (default 64).

    Returns
    -------
    List of dicts, each with keys:
        text         – the chunk string
        source       – the value passed as *source*
        chunk_index  – zero-based position within this document
        metadata     – dict with char_count
    """
    pieces = _split_recursive(text, _SEPARATORS, chunk_size)
    raw_chunks = _merge_with_overlap(pieces, chunk_size, overlap)

    return [
        {
            "text": chunk,
            "source": source,
            "chunk_index": i,
            "metadata": {"char_count": len(chunk)},
        }
        for i, chunk in enumerate(raw_chunks)
        if chunk
    ]
