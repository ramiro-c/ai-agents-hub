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


def embed_batch(texts: list[str] | tuple[str, ...]) -> list[list[float]]:
    """Return L2-normalized embeddings for each text (one encode call)."""
    return _model().encode(list(texts), normalize_embeddings=True).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product; equals cosine when both vectors are L2-normalized."""
    return sum(x * y for x, y in zip(a, b, strict=True))
