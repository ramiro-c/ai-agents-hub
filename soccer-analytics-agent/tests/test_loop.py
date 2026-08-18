from types import SimpleNamespace

from google.genai import errors, types
from soccer_agent.loop import run_turn


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
