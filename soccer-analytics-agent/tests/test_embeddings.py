import math

import pytest


def test_cosine_similarity_identical_unit_vectors():
    from soccer_agent.embeddings import cosine_similarity

    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    from soccer_agent.embeddings import cosine_similarity

    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


@pytest.mark.integration
def test_embed_dimension_and_normalization():
    from soccer_agent.embeddings import DIM, embed

    vec = embed("Argentina won the World Cup")
    assert len(vec) == DIM
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3  # normalized


@pytest.mark.integration
def test_embed_similar_texts_closer_than_unrelated():
    from soccer_agent.embeddings import cosine_similarity, embed

    goal = embed("Messi scored a goal")
    similar = embed("Messi found the net")
    unrelated = embed("The stadium roof needs repairs")

    assert cosine_similarity(goal, similar) > cosine_similarity(goal, unrelated)
