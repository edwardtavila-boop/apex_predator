"""
EVOLUTIONARY TRADING ALGO // jarvis.memory.voyage_adapter
=============================================
Production adapter for voyage-3-large embeddings (1024-dim).

The adapter satisfies the same `EmbeddingPipeline` Protocol as the
deterministic local embedder, so wiring it in is one line:

    embedder = (
        VoyageEmbedderAdapter() if voyage_available()
        else DeterministicEmbedder(dim=1024)
    )

Lazy imports + env-controlled API key + retry/backoff are wrapped so
the adapter degrades gracefully when:
  * the `voyageai` package is not installed
  * VOYAGEAI_API_KEY is not set in the env
  * the API returns a transient error

All three cases raise RuntimeError with an actionable message; never
returns garbage.

The factory `voyage_available()` returns False without invoking the
client if any of the above hold; tests use the deterministic embedder
and production wires the voyage adapter via the env check.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from eta_engine.jarvis.memory.embeddings import EmbeddingPipeline

DEFAULT_MODEL = "voyage-3-large"
DEFAULT_DIM = 1024


def voyage_available() -> bool:
    """True iff the voyage SDK is importable AND an API key is present."""
    if not os.environ.get("VOYAGEAI_API_KEY"):
        return False
    try:
        import voyageai  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


class VoyageEmbedderAdapter:
    """voyage-3-large adapter. Use only when voyage_available() is True."""

    name = "voyage-3-large"
    dim = DEFAULT_DIM

    def __init__(self, *, model: str = DEFAULT_MODEL, timeout_s: float = 30.0, retries: int = 2) -> None:
        if not voyage_available():
            raise RuntimeError(
                "VoyageEmbedderAdapter requires `pip install voyageai` AND "
                "VOYAGEAI_API_KEY in env. Use DeterministicEmbedder for tests."
            )
        import voyageai  # type: ignore

        self._client = voyageai.Client(
            api_key=os.environ["VOYAGEAI_API_KEY"],
        )
        self.model = model
        self.timeout_s = timeout_s
        self.retries = max(0, int(retries))

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        text_list = list(texts)
        if not text_list:
            return []
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._client.embed(
                    text_list,
                    model=self.model,
                    input_type="document",
                )
                # voyageai returns .embeddings (List[List[float]])
                vecs = resp.embeddings
                if not vecs or len(vecs) != len(text_list):
                    raise RuntimeError(f"voyage returned {len(vecs)} vectors for {len(text_list)} inputs")
                return [list(v) for v in vecs]
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt >= self.retries:
                    break
        raise RuntimeError(
            f"voyage embedding failed after {self.retries + 1} attempts: {type(last_err).__name__}: {last_err}"
        )


def make_embedder() -> "EmbeddingPipeline":
    """Factory: voyage if available, else deterministic local embedder."""
    if voyage_available():
        return VoyageEmbedderAdapter()
    from eta_engine.jarvis.memory.embeddings import DeterministicEmbedder

    return DeterministicEmbedder(dim=DEFAULT_DIM)
