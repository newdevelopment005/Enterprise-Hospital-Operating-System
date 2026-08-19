"""Pure-Python vector search over JSON-array embeddings.

Embeddings are stored as JSONB float arrays (works on Postgres and in-memory
SQLite alike). Cosine similarity is computed here; a production Postgres could
swap this for a pgvector index without changing the interface.
"""

from __future__ import annotations

import math


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


def l2(vector: list[float]) -> list[float]:
    """L2-normalize in place."""
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]