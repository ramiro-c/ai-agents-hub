from types import SimpleNamespace

import pytest
from google.genai import errors, types
from soccer_agent.loop import (
    CHALLENGE_REASK,
    COVERAGE_REASK,
    GROUNDING_REASK,
    SYSTEM_PROMPT,
    TRUNCATION_REASK,
    _is_coverage_overclaim,
    run_turn,
)


class FakeModels:
    """Scripted Gemini: first turn calls a tool, second turn answers."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(contents)
        return self._responses.pop(0)

    def generate_content_stream(self, *, model, contents, config):
        # The real client streams; each scripted response is emitted as a
        # single chunk (its candidate/content/parts shape matches a chunk).
        # A scripted response given as a *list* is emitted as a multi-chunk
        # stream, for guard/regression tests that mix empty and valid chunks.
        self.calls.append(contents)
        response = self._responses.pop(0)
        if isinstance(response, list):
            yield from response
        else:
            yield response


def _response(parts):
    content = types.Content(role="model", parts=parts)
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


def _model_call_text(fake, call_index: int) -> str:
    return "".join(
        getattr(part, "text", "") or ""
        for content in fake.models.calls[call_index]
        for part in content.parts
    )


class RateLimitedModels:
    """Scripted Gemini: 429 quota error on the first N stream calls, then answers."""

    def __init__(self, error_calls, response):
        self._error_calls = error_calls
        self._response = response
        self.calls = 0

    def generate_content_stream(self, *, model, contents, config):
        if self.calls < self._error_calls:
            self.calls += 1
            raise errors.ClientError(
                code=429,
                response_json={
                    "error": {
                        "code": 429,
                        "message": "RESOURCE_EXHAUSTED",
                        "status": "RESOURCE_EXHAUSTED",
                    }
                },
            )
        self.calls += 1
        yield self._response


def test_run_turn_dispatches_tool_then_answers(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "soccer_agent.loop.dispatch",
        lambda name, args: calls.append((name, args)) or {"rows": [["49000"]]},
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": "SELECT count(*) FROM matches"},
                        )
                    ]
                ),
                _response([types.Part(text="There are 49,000 matches.")]),
            ]
        )
    )

    answer, history, steps = run_turn(
        fake, [], "How many matches are there?", model="test"
    )

    assert calls == [("sql_query", {"sql": "SELECT count(*) FROM matches"})]
    assert answer == "There are 49,000 matches."
    # history: user msg, model tool call, tool response, model answer
    assert len(history) == 4


def test_run_turn_plain_answer_no_tools():
    fake = SimpleNamespace(models=FakeModels([_response([types.Part(text="Hi!")])]))
    answer, history, steps = run_turn(fake, [], "hello", model="test")
    assert answer == "Hi!"
    assert len(history) == 2


def test_run_turn_skips_empty_candidates_chunk():
    """A safety-block / MAX_TOKENS chunk with no candidates must be skipped."""
    fake = SimpleNamespace(
        models=FakeModels(
            [
                [
                    SimpleNamespace(candidates=[]),
                    _response([types.Part(text="Fine.")]),
                ]
            ]
        )
    )
    answer, history, steps = run_turn(fake, [], "hello", model="test")
    assert answer == "Fine."
    assert len(history) == 2  # user message + model answer, no empty turn


def test_run_turn_skips_chunk_with_none_parts():
    """A candidate whose content.parts is None must be skipped, not crashed on."""
    none_parts = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=None))]
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                [
                    none_parts,
                    _response([types.Part(text="Fine.")]),
                ]
            ]
        )
    )
    answer, history, steps = run_turn(fake, [], "hello", model="test")
    assert answer == "Fine."
    assert len(history) == 2


def test_run_turn_all_empty_chunks_answers_gracefully():
    """A turn whose chunks are ALL empty completes with fallback text."""
    none_parts = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=None))]
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                [
                    SimpleNamespace(candidates=[]),
                    none_parts,
                ]
            ]
        )
    )
    answer, history, steps = run_turn(fake, [], "hello", model="test")
    assert answer  # graceful fallback, never an empty answer
    assert "could not" in answer
    assert len(history) == 1  # only the user message; no empty model turn


def test_run_turn_retries_on_429_rate_limit(monkeypatch):
    """A Vertex 429 (per-minute quota) is retried with backoff, never crashing."""
    sleeps = []
    monkeypatch.setattr("soccer_agent.loop.time.sleep", sleeps.append)
    fake = SimpleNamespace(
        models=RateLimitedModels(
            error_calls=2, response=_response([types.Part(text="Fine.")])
        )
    )

    answer, history, steps = run_turn(fake, [], "hello", model="test")

    assert fake.models.calls == 3  # 2 rate-limited attempts + 1 success
    assert sleeps == [2.0, 4.0]  # exponential backoff: base 2s * 2**attempt
    assert answer == "Fine."
    assert len(history) == 2  # user message + model answer, no empty turn


def test_system_prompt_enforces_tool_grounding():
    """Match facts must be tool-backed; the model must never answer from memory."""
    assert "GROUNDING" in SYSTEM_PROMPT
    assert "ALWAYS call a" in SYSTEM_PROMPT
    assert "not a fact in this conversation" in SYSTEM_PROMPT
    # A challenged, tool-backed answer must never be retracted from parametric memory.
    assert "tool-backed positive fact" in SYSTEM_PROMPT
    assert "parametric memory" in SYSTEM_PROMPT
    assert "re-verify with a tool call" in SYSTEM_PROMPT
    # Coverage: missing data ≠ event did not happen.
    assert "COVERAGE" in SYSTEM_PROMPT
    assert "lacks evidence, not that the event did not occur" in SYSTEM_PROMPT
    assert "state exactly what the database shows" in SYSTEM_PROMPT
    assert "July 2026" not in SYSTEM_PROMPT
    assert "last data update" not in SYSTEM_PROMPT.lower()
    assert "July 2026" not in CHALLENGE_REASK
    assert "last data update" not in CHALLENGE_REASK.lower()


def test_run_turn_grounding_nudge_forces_tool_on_factual_question(monkeypatch):
    """A text-only answer to a match question triggers ONE tool-forcing re-ask."""
    calls = []
    monkeypatch.setattr(
        "soccer_agent.loop.dispatch",
        lambda name, args: (
            calls.append((name, args)) or {"rows": [["Spain 1 - 0 Argentina"]]}
        ),
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                # 1) hallucination: answers from memory, no tool call
                _response(
                    [types.Part(text="The 2026 World Cup has not been played yet.")]
                ),
                # 2) after the grounding nudge: finally calls a tool
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": "SELECT * FROM matches"},
                        )
                    ]
                ),
                # 3) grounded answer from the tool result
                _response([types.Part(text="Spain beat Argentina 1-0 in the final.")]),
            ]
        )
    )

    answer, history, steps = run_turn(
        fake, [], "who won the 2026 World Cup?", model="test"
    )

    # The nudge appears in the second model call's history (last user part).
    second_call_texts = _model_call_text(fake, 1)
    assert "call a tool" in second_call_texts
    # Tool was actually dispatched after the nudge.
    assert calls and calls[0][0] == "sql_query"
    # Final answer is grounded.
    assert "Spain" in answer and "1-0" in answer
    # history: user msg, hallucinated answer, nudge, tool call, result, answer = 6
    assert len(history) == 6


def test_run_turn_grounding_nudge_never_fires_for_chit_chat():
    """Non-factual questions are never forced into a tool round."""
    fake = SimpleNamespace(models=FakeModels([_response([types.Part(text="Hi!")])]))
    answer, history, steps = run_turn(fake, [], "hello", model="test")
    assert answer == "Hi!"
    assert len(history) == 2
    assert len(fake.models.calls) == 1  # no extra nudge round


def test_run_turn_truncation_nudge_forces_refined_query(monkeypatch):
    """A truncated tool result followed by a text-only answer triggers ONE re-ask."""
    fetch_calls = []

    def _dispatch(name, args):
        fetch_calls.append((name, args))
        if "LIMIT 1" in args.get("sql", ""):
            return {"rows": [["Spain", "Argentina", 1, 0]]}
        return {
            "rows": [["dummy"]] * 50,
            "truncated": True,
        }

    broad_sql = (
        "SELECT home_team, away_team, home_score, away_score "
        "FROM matches WHERE tournament ILIKE '%World Cup%'"
    )
    refined_sql = (
        "SELECT home_team, away_team, home_score, away_score "
        "FROM matches WHERE tournament = 'FIFA World Cup' "
        "ORDER BY match_date DESC LIMIT 1"
    )
    monkeypatch.setattr("soccer_agent.loop.dispatch", _dispatch)
    fake = SimpleNamespace(
        models=FakeModels(
            [
                # 1) broad query: tool call that returns a truncated sample
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": broad_sql},
                        )
                    ]
                ),
                # 2) after the truncated result, the model answers from the sample
                _response(
                    [types.Part(text="Only preliminary matches are in the sample.")]
                ),
                # 3) after the truncation nudge: a more specific tool call
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": refined_sql},
                        )
                    ]
                ),
                # 4) grounded answer from the refined tool result
                _response([types.Part(text="Spain beat Argentina 1-0 in the final.")]),
            ]
        )
    )

    answer, history, steps = run_turn(
        fake, [], "who won the 2026 World Cup?", model="test"
    )

    third_call_texts = _model_call_text(fake, 2)
    assert TRUNCATION_REASK in third_call_texts
    assert len(fetch_calls) == 2
    assert "LIMIT 1" not in fetch_calls[0][1]["sql"]
    assert "LIMIT 1" in fetch_calls[1][1]["sql"]
    assert "Spain" in answer and "1-0" in answer
    assert len(history) == 8


def test_run_turn_truncation_nudge_never_fires_without_truncated_flag(monkeypatch):
    """A complete tool result must not trigger the truncation re-ask."""
    fetch_calls = []

    def _dispatch(name, args):
        fetch_calls.append((name, args))
        return {"rows": [["Spain", "Argentina", 1, 0]]}

    monkeypatch.setattr("soccer_agent.loop.dispatch", _dispatch)
    fake = SimpleNamespace(
        models=FakeModels(
            [
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": "SELECT * FROM matches LIMIT 1"},
                        )
                    ]
                ),
                _response([types.Part(text="Spain beat Argentina 1-0 in the final.")]),
            ]
        )
    )

    answer, history, steps = run_turn(
        fake, [], "who won the 2026 World Cup?", model="test"
    )

    assert len(fetch_calls) == 1
    assert "Spain" in answer
    assert len(fake.models.calls) == 2
    assert TRUNCATION_REASK not in _model_call_text(fake, 1)
    assert len(history) == 4


def test_is_coverage_overclaim_honest_ignorance_is_false():
    """Honest 'not in this dataset' copy must not trip the overclaim detector."""
    assert (
        _is_coverage_overclaim("I don't have that information in this dataset") is False
    )


def test_is_coverage_overclaim_detects_non_occurrence_phrases():
    """Lexical non-occurrence phrases must trip the overclaim detector."""
    assert _is_coverage_overclaim("the tournament would not have concluded") is True
    assert _is_coverage_overclaim("That tournament has not taken place yet.") is True
    assert (
        _is_coverage_overclaim(
            "The tournament would not have concluded; "
            "that match is not in this dataset."
        )
        is True
    )


def _incomplete_coverage_history():
    """Prior turn: tool ran but the answer reflected incomplete coverage."""
    return [
        types.Content(
            role="user",
            parts=[types.Part(text="who won the 2026 World Cup?")],
        ),
        types.Content(
            role="model",
            parts=[
                types.Part.from_function_call(
                    name="sql_query",
                    args={"sql": "SELECT home_team, away_team FROM matches LIMIT 5"},
                )
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part.from_function_response(
                    name="sql_query",
                    response={
                        "result": {
                            "rows": [
                                ["Brazil", "Serbia"],
                                ["Germany", "Japan"],
                            ],
                        }
                    },
                )
            ],
        ),
        types.Content(
            role="model",
            parts=[
                types.Part(
                    text="I found some group-stage rows but no clear final result "
                    "in this dataset."
                )
            ],
        ),
    ]


def test_run_turn_coverage_overclaim_nudge_after_challenge_pushback():
    """Pushback after incomplete coverage: challenge then coverage on text overclaim."""
    overclaim = "The tournament would not have concluded."
    honest_answer = (
        "I don't have that information in this dataset. "
        "Try a more specific query for the final, or check with a human."
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                _response([types.Part(text=overclaim)]),
                _response([types.Part(text=overclaim)]),
                _response([types.Part(text=honest_answer)]),
            ]
        )
    )

    history = _incomplete_coverage_history()
    answer, history, steps = run_turn(fake, history, "are you sure?", model="test")

    assert CHALLENGE_REASK in _model_call_text(fake, 1)
    assert COVERAGE_REASK in _model_call_text(fake, 2)
    assert "in this dataset" in answer.lower()
    assert "would not have concluded" not in answer.lower()


def test_run_turn_coverage_overclaim_nudge_after_tools(monkeypatch):
    """A post-tool overclaim triggers ONE coverage re-ask and an honest follow-up."""
    fetch_calls = []

    def _dispatch(name, args):
        fetch_calls.append((name, args))
        return {
            "rows": [
                ["Brazil", "Serbia", 2, 0],
                ["Germany", "Japan", 1, 2],
                ["Spain", "Costa Rica", 7, 0],
            ],
        }

    group_sql = (
        "SELECT home_team, away_team, home_score, away_score "
        "FROM matches WHERE tournament = 'FIFA World Cup' "
        "AND match_date < DATE '2022-12-18'"
    )
    monkeypatch.setattr("soccer_agent.loop.dispatch", _dispatch)
    overclaim = "the tournament would not have concluded"
    honest_answer = (
        "I don't have that information in this dataset. "
        "Try a more specific query for the final match, or check with a human."
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": group_sql},
                        )
                    ]
                ),
                _response([types.Part(text=overclaim)]),
                _response([types.Part(text=honest_answer)]),
            ]
        )
    )

    answer, history, steps = run_turn(
        fake, [], "who won the 2026 World Cup?", model="test"
    )

    third_call_texts = _model_call_text(fake, 2)
    assert COVERAGE_REASK in third_call_texts
    assert len(fetch_calls) == 1
    assert "in this dataset" in answer.lower()
    assert "would not have concluded" not in answer.lower()
    assert len(history) == 6


def test_run_turn_error_retry_after_bad_query(monkeypatch):
    """A failed tool round followed by a text-only answer triggers ONE retry nudge."""
    fetch_calls = []

    def _dispatch(name, args):
        fetch_calls.append((name, args))
        if "winner" in args.get("sql", ""):
            return {"error": 'column "winner" does not exist'}
        return {"rows": [["Spain", "Argentina", 1, 0]]}

    good_sql = (
        "SELECT home_team, away_team, home_score, away_score "
        "FROM matches WHERE tournament ILIKE '%World Cup%' "
        "ORDER BY match_date DESC LIMIT 5"
    )
    monkeypatch.setattr("soccer_agent.loop.dispatch", _dispatch)
    fake = SimpleNamespace(
        models=FakeModels(
            [
                # 1) bad query: tool call that will ERROR (no winner column)
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": "SELECT winner FROM matches"},
                        )
                    ]
                ),
                # 2) after the error result, the model answers from memory
                _response(
                    [types.Part(text="That tournament has not taken place yet.")]
                ),
                # 3) after the error-retry nudge: a GOOD tool call
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": good_sql},
                        )
                    ]
                ),
                # 4) grounded answer from the good tool result
                _response([types.Part(text="Spain beat Argentina 1-0 in the final.")]),
            ]
        )
    )

    answer, history, steps = run_turn(
        fake, [], "who won the 2026 World Cup?", model="test"
    )

    # The error-retry nudge appears in the third model call's history.
    third_call_texts = _model_call_text(fake, 2)
    assert "failed with an error" in third_call_texts
    # Two tool rounds dispatched: the bad query and the fixed query.
    assert len(fetch_calls) == 2
    assert "winner" in fetch_calls[0][1]["sql"]
    assert "home_score" in fetch_calls[1][1]["sql"]
    # Final answer is grounded, not a memory hallucination.
    assert "Spain" in answer and "1-0" in answer
    # user, bad call, error result, text answer, nudge, good call, result, answer
    assert len(history) == 8


def _grounded_history():
    """History where a previous turn answered with tool-backed evidence."""
    return [
        types.Content(
            role="user",
            parts=[types.Part(text="quien gano el mundial 2026?")],
        ),
        types.Content(
            role="model",
            parts=[
                types.Part.from_function_call(
                    name="sql_query",
                    args={
                        "sql": (
                            "SELECT match_date, home_team, away_team, home_score, "
                            "away_score FROM matches WHERE tournament = 'FIFA World "
                            "Cup' AND EXTRACT(YEAR FROM match_date) = 2026 "
                            "ORDER BY match_date DESC LIMIT 1"
                        )
                    },
                )
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part.from_function_response(
                    name="sql_query",
                    response={
                        "result": {"rows": [["2026-07-19", "Spain", "Argentina", 1, 0]]}
                    },
                )
            ],
        ),
        types.Content(
            role="model",
            parts=[
                types.Part(
                    text="Según la base de datos, España venció a Argentina 1-0 "
                    "en la final del 19 de julio de 2026."
                )
            ],
        ),
    ]


def test_run_turn_challenge_nudge_forces_reverification(monkeypatch):
    """A challenged grounded answer ('¿cómo?') must re-verify, not retract."""
    calls = []
    monkeypatch.setattr(
        "soccer_agent.loop.dispatch",
        lambda name, args: (
            calls.append((name, args))
            or {"rows": [["2026-07-19", "Spain", "Argentina", 1, 0]]}
        ),
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                # 1) challenge "¿cómo?" answered from memory WITHOUT a tool call
                _response(
                    [types.Part(text="El Mundial de 2026 no se ha jugado todavía...")]
                ),
                # 2) after the challenge nudge: re-runs the verification query
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": "SELECT * FROM matches"},
                        )
                    ]
                ),
                # 3) grounded answer, evidence from the tool result
                _response(
                    [types.Part(text="España venció a Argentina 1-0 el 19 de julio.")]
                ),
            ]
        )
    )

    history = _grounded_history()
    answer, history, steps = run_turn(fake, history, "como?", model="test")

    # The challenge nudge appears in the second model call's history.
    second_call_texts = _model_call_text(fake, 1)
    assert CHALLENGE_REASK in second_call_texts
    # Tool was dispatched to re-verify after the nudge.
    assert calls and calls[0][0] == "sql_query"
    # Final answer keeps the grounded fact instead of retracting.
    assert "España" in answer and "1-0" in answer
    # History grew: prior 4 + user msg, retraction, nudge, tool call, result, answer
    assert len(history) == 10


def test_run_turn_challenge_nudge_never_fires_for_chit_chat():
    """A plain non-challenge follow-up must not force a tool round."""
    fake = SimpleNamespace(models=FakeModels([_response([types.Part(text="Bien!")])]))
    answer, history, steps = run_turn(fake, [], "¿cómo estás?", model="test")
    assert answer == "Bien!"
    assert len(history) == 2
    assert len(fake.models.calls) == 1  # no extra nudge round


def test_run_turn_challenge_nudge_skipped_without_prior_answer():
    """A first-turn lexical challenge must not inject CHALLENGE_REASK."""
    fake = SimpleNamespace(models=FakeModels([_response([types.Part(text="Ok")])]))
    answer, history, steps = run_turn(fake, [], "como?", model="test")
    assert answer == "Ok"
    assert len(fake.models.calls) == 1
    assert CHALLENGE_REASK not in _model_call_text(fake, 0)


def test_run_turn_challenge_nudge_fires_after_text_only_prior_answer():
    """Working memory is text-only; a prior model turn is enough to challenge."""
    fake = SimpleNamespace(
        models=FakeModels(
            [
                _response([types.Part(text="No se ha jugado.")]),
                _response([types.Part(text="España 1-0 Argentina.")]),
            ]
        )
    )
    prior = [
        types.Content(role="user", parts=[types.Part(text="hola")]),
        types.Content(role="model", parts=[types.Part(text="hola!")]),
    ]
    answer, history, steps = run_turn(fake, prior, "como?", model="test")
    assert CHALLENGE_REASK in _model_call_text(fake, 1)
    assert len(fake.models.calls) == 2
    assert "España" in answer


def test_run_turn_grounding_uses_classify_as_not_user_message():
    """Match vocabulary in episodic context must not trigger the grounding nudge."""
    fake = SimpleNamespace(models=FakeModels([_response([types.Part(text="Hola!")])]))
    augmented = (
        "Relevant context from earlier in this session:\n"
        "- Earlier you asked: 'who won the 2026 World Cup match?' -> 'Spain won'\n\n"
        "Current question: hola"
    )
    answer, history, steps = run_turn(
        fake,
        [],
        augmented,
        model="test",
        classify_as="hola",
    )
    assert answer == "Hola!"
    assert len(fake.models.calls) == 1
    assert GROUNDING_REASK not in _model_call_text(fake, 0)


def test_run_turn_challenge_uses_classify_as_not_user_message():
    """Lexical hints in episodic context must not trigger the challenge nudge."""
    fake = SimpleNamespace(
        models=FakeModels([_response([types.Part(text="He plays for Inter Miami.")])])
    )
    prior = [
        types.Content(role="user", parts=[types.Part(text="hola")]),
        types.Content(role="model", parts=[types.Part(text="hola!")]),
    ]
    augmented = (
        "Relevant context from earlier in this session:\n"
        "- Earlier you asked: 'who won?' -> 'that is wrong, Spain won'\n\n"
        "Current question: Where does Messi play now?"
    )
    answer, history, steps = run_turn(
        fake,
        prior,
        augmented,
        model="test",
        classify_as="Where does Messi play now?",
    )
    assert answer == "He plays for Inter Miami."
    assert len(fake.models.calls) == 1
    assert CHALLENGE_REASK not in _model_call_text(fake, 0)


@pytest.mark.integration
def test_run_turn_semantic_challenge_nudge_forces_reverification(monkeypatch):
    """A challenge paraphrase NOT in the lexical hints still fires the nudge.

    The MiniLM semantic layer must catch phrases like "no te creo" (cosine
    0.845 vs challenge exemplars) that the hardcoded hint list misses.
    """
    from soccer_agent.loop import _CHALLENGE_HINTS

    # Precondition: this phrase is NOT covered by the lexical layer, so the
    # nudge can only have fired through the semantic layer.
    assert not any(h in "no te creo" for h in _CHALLENGE_HINTS)

    # Skip cleanly when the local embedding model is unavailable (offline).
    try:
        from soccer_agent.embeddings import embed

        embed("ping")
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"MiniLM unavailable for semantic test: {exc}")

    calls = []
    monkeypatch.setattr(
        "soccer_agent.loop.dispatch",
        lambda name, args: (
            calls.append((name, args))
            or {"rows": [["2026-07-19", "Spain", "Argentina", 1, 0]]}
        ),
    )
    fake = SimpleNamespace(
        models=FakeModels(
            [
                _response([types.Part(text="No te creo, eso es de tu memoria.")]),
                _response(
                    [
                        types.Part.from_function_call(
                            name="sql_query",
                            args={"sql": "SELECT * FROM matches"},
                        )
                    ]
                ),
                _response(
                    [types.Part(text="España venció a Argentina 1-0 el 19 de julio.")]
                ),
            ]
        )
    )

    history = _grounded_history()
    answer, history, steps = run_turn(fake, history, "no te creo", model="test")

    # The challenge nudge appears in the second model call's history.
    second_call_texts = _model_call_text(fake, 1)
    assert CHALLENGE_REASK in second_call_texts
    # Tool was dispatched to re-verify after the nudge.
    assert calls and calls[0][0] == "sql_query"
    # Final answer keeps the grounded fact instead of retracting.
    assert "España" in answer and "1-0" in answer


def test_semantic_is_challenge_degrades_on_vector_mismatch(monkeypatch):
    from soccer_agent.loop import _challenge_exemplar_vectors, _semantic_is_challenge

    _challenge_exemplar_vectors.cache_clear()
    short_dummy = [1.0, 0.0, 0.0]
    long_dummy = [1.0, 0.0, 0.0, 0.0]

    def fake_embed_batch(texts):
        return [short_dummy] * len(texts)

    monkeypatch.setattr("soccer_agent.embeddings.embed_batch", fake_embed_batch)
    monkeypatch.setattr("soccer_agent.embeddings.embed", lambda text: long_dummy)

    try:
        assert _semantic_is_challenge("hello") is False
    finally:
        _challenge_exemplar_vectors.cache_clear()


def test_challenge_exemplar_vectors_cached(monkeypatch):
    from soccer_agent.loop import _challenge_exemplar_vectors, _semantic_is_challenge

    _challenge_exemplar_vectors.cache_clear()
    batch_calls = 0
    dummy = [1.0, 0.0, 0.0]

    def fake_embed_batch(texts):
        nonlocal batch_calls
        batch_calls += 1
        return [dummy] * len(texts)

    monkeypatch.setattr("soccer_agent.embeddings.embed_batch", fake_embed_batch)
    monkeypatch.setattr("soccer_agent.embeddings.embed", lambda text: dummy)

    try:
        _semantic_is_challenge("first")
        _semantic_is_challenge("second")
        assert batch_calls == 1
    finally:
        _challenge_exemplar_vectors.cache_clear()


def test_is_challenge_lexical_gate_skips_semantic(monkeypatch):
    from soccer_agent.loop import _is_challenge

    def fail_semantic(_message):
        raise AssertionError("semantic layer must not run for lexical match")

    monkeypatch.setattr("soccer_agent.loop._semantic_is_challenge", fail_semantic)

    assert _is_challenge("como?") is True
