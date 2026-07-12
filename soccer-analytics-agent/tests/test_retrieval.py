"""Unit tests for RRF fusion logic."""

from soccer_agent.retrieval import rrf_fuse


def test_rrf_fuses_two_rankings():
    vec = [
        {"id": 42, "content": "doc 42"},
        {"id": 17, "content": "doc 17"},
        {"id": 88, "content": "doc 88"},
    ]
    txt = [
        {"id": 17, "content": "doc 17"},
        {"id": 88, "content": "doc 88"},
        {"id": 42, "content": "doc 42"},
    ]
    result = rrf_fuse(vec, txt, k=60, top_n=5)

    # doc 17 ranks high in both (2nd in vec, 1st in txt) — should be first
    assert result[0]["id"] == 17
    # All three should appear
    ids = {r["id"] for r in result}
    assert ids == {17, 42, 88}


def test_rrf_doc_in_only_one_list_still_scores():
    vec = [{"id": 1, "content": "a"}]
    txt = [{"id": 2, "content": "b"}]
    result = rrf_fuse(vec, txt, k=60, top_n=5)
    assert len(result) == 2


def test_rrf_respects_top_n():
    vec = [{"id": i, "content": str(i)} for i in range(20)]
    txt = []
    result = rrf_fuse(vec, txt, k=60, top_n=3)
    assert len(result) == 3
