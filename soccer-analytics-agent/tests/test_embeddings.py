import math

import pytest


@pytest.mark.integration
def test_embed_dimension_and_normalization():
    from soccer_agent.embeddings import DIM, embed

    vec = embed("Argentina won the World Cup")
    assert len(vec) == DIM
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3  # normalized


@pytest.mark.integration
def test_embed_similar_texts_closer_than_unrelated():
    from soccer_agent.embeddings import embed

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))

    goal = embed("Messi scored a goal")
    similar = embed("Messi found the net")
    unrelated = embed("The stadium roof needs repairs")

    assert cosine(goal, similar) > cosine(goal, unrelated)
