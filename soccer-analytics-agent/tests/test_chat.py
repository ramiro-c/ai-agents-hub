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


def test_respond_passes_raw_utterance_as_classify_as(monkeypatch):
    captured = {}

    def fake_run_turn(
        client, history, user_message, model, trace_ctx=None, classify_as=None
    ):
        captured["user_message"] = user_message
        captured["classify_as"] = classify_as
        return "ok", history, 1

    monkeypatch.setattr(chat, "run_turn", fake_run_turn)
    monkeypatch.setattr(chat.memory, "load_working", lambda s, limit=10: [])
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
    monkeypatch.setattr(chat.memory, "append_working", lambda s, r, c: None)
    monkeypatch.setattr(chat.memory, "save_episode", lambda s, u, a: None)
    monkeypatch.setattr(chat.trace, "get_last_turn_id", lambda s: 0)

    fake = SimpleNamespace(models=FakeModels("unused"))
    chat.respond(fake, "sess-1", "Where does he play now?", model="test")

    assert captured["classify_as"] == "Where does he play now?"
    assert "Messi" in captured["user_message"]
    assert "Where does he play now?" in captured["user_message"]


def test_respond_stream_passes_raw_utterance_as_classify_as(monkeypatch):
    captured = {}

    def fake_run_turn_events(
        client, history, user_message, model, trace_ctx=None, classify_as=None
    ):
        captured["user_message"] = user_message
        captured["classify_as"] = classify_as
        yield {"type": "done", "answer": "ok"}

    monkeypatch.setattr(chat, "run_turn_events", fake_run_turn_events)
    monkeypatch.setattr(chat.memory, "load_working", lambda s, limit=10: [])
    monkeypatch.setattr(chat.memory, "recall_episodes", lambda s, q, k=3: [])
    monkeypatch.setattr(chat.memory, "append_working", lambda s, r, c: None)
    monkeypatch.setattr(chat.memory, "save_episode", lambda s, u, a: None)
    monkeypatch.setattr(chat.trace, "get_last_turn_id", lambda s: 0)

    fake = SimpleNamespace(models=FakeModels("unused"))
    events = list(chat.respond_stream(fake, "sess-1", "hola", model="test"))

    assert captured["classify_as"] == "hola"
    assert captured["user_message"] == "hola"  # no episodes → not augmented
    assert events[-1]["type"] == "done"
