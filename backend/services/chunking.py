"""
Text chunking service for RAG.

Splits text into chunks using separator-based splitting (paragraphs, sentences).
No LangChain dependency — pure Python implementation.

Chunk sizing:
- Default chunk_size: ~500 tokens (≈1500 chars for mixed FA/EN)
- Overlap: ~50 tokens (≈150 chars)
- Token estimation: ~3 chars per token for mixed content
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 1500     # chars (~500 tokens at 3 chars/token)
DEFAULT_CHUNK_OVERLAP = 150   # chars (~50 tokens)
CHARS_PER_TOKEN = 3           # estimate for mixed Persian/English


def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Persian/English text."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """Split text into overlapping chunks.

    Strategy:
    1. Split by paragraphs (\n\n)
    2. If a paragraph is too long, split by sentences
    3. If a sentence is still too long, split by character limit

    Returns list of dicts: {content, token_estimate, index}
    """
    if not text or not text.strip():
        return []

    # Normalize whitespace but preserve paragraph breaks
    text = text.strip()

    # Split into paragraphs
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    # Build chunks
    chunks: list[str] = []
    current = ''

    for para in paragraphs:
        # If paragraph fits in current chunk, add it
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
            continue

        # If current is non-empty, save it and start fresh
        if current:
            chunks.append(current.strip())
            current = ''

        # If paragraph itself is too long, split by sentences
        if len(para) > chunk_size:
            sub_chunks = _split_by_sentences(para, chunk_size)
            chunks.extend(sub_chunks)
        else:
            current = para

    if current.strip():
        chunks.append(current.strip())

    # Apply overlap
    if chunk_overlap > 0 and len(chunks) > 1:
        chunks = _apply_overlap(chunks, chunk_overlap)

    # Build result
    result = []
    for i, chunk in enumerate(chunks):
        result.append({
            'content': chunk,
            'token_estimate': estimate_tokens(chunk),
            'index': i,
        })

    return result


def _split_by_sentences(text: str, max_size: int) -> list[str]:
    """Split text by sentence boundaries, respecting max_size."""
    # Split on sentence-ending punctuation (supports Persian and English)
    sentences = re.split(r'(?<=[.!?\n])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    current = ''

    for sent in sentences:
        if len(current) + len(sent) + 1 <= max_size:
            current = f"{current} {sent}" if current else sent
        else:
            if current:
                chunks.append(current.strip())
            # If sentence itself is too long, force-split
            if len(sent) > max_size:
                while len(sent) > max_size:
                    chunks.append(sent[:max_size])
                    sent = sent[max_size:]
                if sent.strip():
                    current = sent
                else:
                    current = ''
            else:
                current = sent

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _apply_overlap(chunks: list[str], overlap_chars: int) -> list[str]:
    """Add overlap from the end of each chunk to the start of the next."""
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        overlap = prev[-overlap_chars:] if len(prev) > overlap_chars else prev
        result.append(f"{overlap} {chunks[i]}")

    return result
