"""Hybrid retrieval: RRF fusion of vector + full-text results."""


def rrf_fuse(
    vector_ranked: list[dict],
    text_ranked: list[dict],
    k: int = 60,
    top_n: int = 5,
) -> list[dict]:
    """Fuse two ranked result lists with Reciprocal Rank Fusion.

    Each item must have an 'id' key. Returns top_n items sorted by RRF score
    descending. The input order determines rank (first = rank 1).
    """
    scores: dict[int, float] = {}
    docs: dict[int, dict] = {}

    for rank, item in enumerate(vector_ranked, start=1):
        doc_id = item["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        docs[doc_id] = item

    for rank, item in enumerate(text_ranked, start=1):
        doc_id = item["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        docs[doc_id] = item  # last writer wins for metadata

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {**docs[doc_id], "rrf_score": round(score, 6)}
        for doc_id, score in ranked[:top_n]
    ]
