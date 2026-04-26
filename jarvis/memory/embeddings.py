"""
EVOLUTIONARY TRADING ALGO // jarvis.memory.embeddings
=========================================
Embedding pipeline. The production target is voyage-3-large at d=1024;
the reference DeterministicEmbedder produces a stable d=1024 vector
without any external API call so tests are reproducible.

Production wiring (when voyage is available) injects a different
implementation behind the same `EmbeddingPipeline` Protocol.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, Protocol, runtime_checkable

DEFAULT_DIM = 1024


@runtime_checkable
class EmbeddingPipeline(Protocol):
    """Sync embedder. Returns one vector per input string."""

    name: str
    dim: int

    def embed(self, texts: Iterable[str]) -> list[list[float]]: ...


def _tokens(text: str) -> list[str]:
    """Crude word tokenizer. Lowercases + splits on non-word."""
    return re.findall(r"\w+", text.lower())


def _hash_to_index(token: str, dim: int) -> int:
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") % dim


class DeterministicEmbedder:
    """Hash-based embedder. NOT semantic — but stable + dependency-free.

    Algorithm: for each token, hash to a vector index ∈ [0, dim) and
    accumulate +1.0 (or +0.5 if the token is short). Vector is L2-
    normalized so cosine similarity behaves like real embeddings.

    Two texts that share many tokens have high cosine similarity.
    Two texts with no overlap have cosine ≈ 0. Good enough for unit
    tests and for the retrieval-impact eval harness.

    Production wiring replaces this with VoyageEmbedder (or similar)
    behind the same Protocol — no caller code changes.
    """

    name = "deterministic"

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self.dim = dim

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in _tokens(t):
                idx = _hash_to_index(tok, self.dim)
                weight = 0.5 if len(tok) <= 2 else 1.0
                v[idx] += weight
            # L2 normalize
            norm = math.sqrt(sum(x * x for x in v))
            if norm > 0:
                v = [x / norm for x in v]
            out.append(v)
        return out


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for L2-normalized vectors == dot product."""
    if len(a) != len(b):
        raise ValueError(f"dim mismatch: {len(a)} vs {len(b)}")
    return sum(x * y for x, y in zip(a, b))
