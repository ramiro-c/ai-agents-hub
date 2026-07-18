from types import SimpleNamespace

from google.genai import types
from soccer_agent import chat


def _answer(text):
    content = types.Content(role="model", parts=[types.Part(text=text)])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


class FakeModels:
    def __init__(self, text):
        self._text = text
        self.last_contents = None

    def generate_content(self, *, model, contents, config):
        self.last_contents = list(
            contents
        )  # copy — run_turn mutates the original after
        return _answer(self._text)

    def generate_content_stream(self, *, model, contents, config):
        # The real client streams; respond() drives run_turn through this path.
        self.last_contents = list(
            contents
        )  # copy — run_turn_events mutates the original after
        yield _answer(self._text)


def test_respond_injects_episodic_grounding_and_persists(monkeypatch):
    saved = {"working": [], "episodes": [], "trace": []}
    monkeypatch.setattr(
        chat.memory,
        "load_working",
        lambda s, limit=10: [("user", "hi"), ("model", "hello")],
    )
    monkeypatch.setattr(
        chat.memory,
        "recall_episodes",
        lambda s, q, k=3: [
            {
                "user_message": "Who is Messi?",
                "agent_response": "An Argentine forward.",
                "score": 0.9,
            }
        ],
    )
    monkeypatch.setattr(
        chat.memory, "append_working", lambda s, r, c: saved["working"].append((r, c))
    )
    monkeypatch.setattr(
        chat.memory, "save_episode", lambda s, u, a: saved["episodes"].append((u, a))
    )
    monkeypatch.setattr(chat.trace, "get_last_turn_id", lambda s: 0)
    monkeypatch.setattr(
        chat.trace,
        "save_step",
        lambda s, t, st, c: saved["trace"].append((t, st, c)),
    )

    fake = SimpleNamespace(models=FakeModels("He plays for Inter Miami."))
    answer, turn_id = chat.respond(
        fake, "sess-1", "Where does he play now?", model="test"
    )

    assert answer == "He plays for Inter Miami."
    assert turn_id == 1  # get_last_turn_id stubbed to 0, so this turn is 1
    # working memory was seeded (2 prior turns) + current user turn = 3 contents sent
    assert len(fake.models.last_contents) == 3
    # episodic grounding was injected into the current user message
    injected = fake.models.last_contents[-1].parts[0].text
    assert "Messi" in injected and "Where does he play now?" in injected
    # the raw (not augmented) turn was persisted to both tiers
    assert saved["working"] == [
        ("user", "Where does he play now?"),
        ("model", "He plays for Inter Miami."),
    ]
    assert saved["episodes"] == [
        ("Where does he play now?", "He plays for Inter Miami.")
    ]
    # tracing was wired — at least one step saved (the model answer)
    assert len(saved["trace"]) >= 1
    assert saved["trace"][0][2]["kind"] == "answer"
