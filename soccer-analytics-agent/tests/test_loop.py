from types import SimpleNamespace

from google.genai import types
from soccer_agent.loop import run_turn


class FakeModels:
    """Scripted Gemini: first turn calls a tool, second turn answers."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(contents)
        return self._responses.pop(0)


def _response(parts):
    content = types.Content(role="model", parts=parts)
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


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
