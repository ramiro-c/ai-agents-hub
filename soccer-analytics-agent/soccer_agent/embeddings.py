"""Local text embeddings via sentence-transformers (all-MiniLM-L6-v2, 384 dims)."""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
DIM = 384


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    """Load the model once per process (first call downloads it)."""
    return SentenceTransformer(MODEL_NAME)


def embed(text: str) -> list[float]:
    """Return a 384-dim L2-normalized embedding for the given text."""
    vec = _model().encode(text, normalize_embeddings=True)
    return vec.tolist()
