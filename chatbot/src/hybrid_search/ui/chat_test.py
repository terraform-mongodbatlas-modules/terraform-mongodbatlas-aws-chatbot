from __future__ import annotations

import pytest

import hybrid_search.ui.chat as chat_module
from hybrid_search.generate import Turn
from hybrid_search.ingest import IngestedFile
from hybrid_search.ui.demo import Mode


class _FakeSession:
    def __init__(self, data: dict | None = None):
        self._data = data or {}

    def get(self, key: str, default: object = None) -> object:
        return self._data.get(key, default)

    def set(self, key: str, value: object) -> None:
        self._data[key] = value


def _patch_session(monkeypatch) -> _FakeSession:
    session = _FakeSession()
    monkeypatch.setattr(chat_module.cl, "user_session", session)
    return session


@pytest.mark.asyncio
async def test_on_message_routes_command_to_mode(monkeypatch):
    session = _patch_session(monkeypatch)
    ran: list[Mode] = []

    async def fake_run(mode: Mode) -> None:
        ran.append(mode)

    monkeypatch.setattr(chat_module, "_run_mode", fake_run)
    message = type("Msg", (), {"command": "Ingest", "content": "", "elements": []})()

    await chat_module.on_message(message)

    assert ran == [Mode.INGEST]
    assert session.get("ui_mode") == "ingest"


@pytest.mark.asyncio
async def test_on_message_routes_demo_text_to_demo_mode(monkeypatch):
    _patch_session(monkeypatch)
    ran: list[Mode] = []

    async def fake_run(mode: Mode) -> None:
        ran.append(mode)

    monkeypatch.setattr(chat_module, "_run_mode", fake_run)
    message = type("Msg", (), {"command": None, "content": "Demo", "elements": []})()

    await chat_module.on_message(message)

    assert ran == [Mode.DEMO]


def test_mode_to_ui_mode_mapping():
    assert chat_module._mode_to_ui_mode(Mode.INGEST) == "ingest"
    assert chat_module._mode_to_ui_mode(Mode.DELETE) == "delete"
    assert chat_module._mode_to_ui_mode(Mode.DEMO) == "query"


@pytest.mark.asyncio
async def test_on_chat_end_closes_the_session_client(monkeypatch):
    session = _patch_session(monkeypatch)
    closed: list[bool] = []

    class _FakeClient:
        def close(self) -> None:
            closed.append(True)

    session.set("client", _FakeClient())

    await chat_module.on_chat_end()

    assert closed == [True]


@pytest.mark.asyncio
async def test_on_chat_end_tolerates_a_missing_client(monkeypatch):
    _patch_session(monkeypatch)

    await chat_module.on_chat_end()


@pytest.mark.asyncio
async def test_delete_file_callback_verifies_the_file_still_exists(monkeypatch):
    _patch_session(monkeypatch)
    deleted: list[list[str]] = []

    async def fake_list(collection):
        return [IngestedFile(file_path="kept.pdf", chunk_count=2)]

    async def fake_perform_delete(**kwargs):
        deleted.append(kwargs["file_paths"])

    async def fake_send() -> None:
        return None

    class _FakeMessage:
        def __init__(self, content: str = "") -> None:
            self.content = content

        async def send(self) -> None:
            await fake_send()

    monkeypatch.setattr(chat_module, "list_ingested_files", fake_list)
    monkeypatch.setattr(chat_module, "_perform_delete", fake_perform_delete)
    monkeypatch.setattr(chat_module.cl, "Message", _FakeMessage)

    stale = type("Action", (), {"payload": {"file_path": "gone.pdf"}})()
    await chat_module.on_delete_file(stale)
    assert deleted == []

    current = type("Action", (), {"payload": {"file_path": "kept.pdf"}})()
    await chat_module.on_delete_file(current)
    assert deleted == [["kept.pdf"]]


@pytest.mark.asyncio
async def test_handle_query_surfaces_failure_description(monkeypatch):
    session = _patch_session(monkeypatch)
    session.set("settings", object())
    session.set("collection", object())
    sent: list[str] = []

    class _FakeMessage:
        def __init__(self, content: str = "") -> None:
            self.content = content

        async def send(self) -> None:
            sent.append(self.content)

    async def fake_index_states(collection, settings):
        return []

    async def fake_run_query_with_steps(*args, **kwargs):
        raise RuntimeError("Unable to locate credentials")

    monkeypatch.setattr(chat_module, "index_states", fake_index_states)
    monkeypatch.setattr(chat_module, "problem_message", lambda states, query: None)
    monkeypatch.setattr(chat_module, "run_query_with_steps", fake_run_query_with_steps)
    monkeypatch.setattr(chat_module.cl, "Message", _FakeMessage)

    await chat_module._handle_query("risk")

    assert sent == ["Query failed: Unable to locate credentials"]


def _patch_query_path(monkeypatch, run_query_with_steps) -> None:
    class _FakeMessage:
        def __init__(self, content: str = "") -> None:
            self.content = content

        async def send(self) -> None:
            return None

    async def fake_index_states(collection, settings):
        return []

    monkeypatch.setattr(chat_module, "index_states", fake_index_states)
    monkeypatch.setattr(chat_module, "problem_message", lambda states, query: None)
    monkeypatch.setattr(chat_module, "run_query_with_steps", run_query_with_steps)
    monkeypatch.setattr(chat_module.cl, "Message", _FakeMessage)


@pytest.mark.asyncio
async def test_handle_query_remembers_turns_for_the_next_question(monkeypatch):
    session = _patch_session(monkeypatch)
    session.set("settings", type("Settings", (), {"llm_history_turns": 1})())
    session.set("collection", object())
    seen: list[list[Turn]] = []

    async def fake_run_query_with_steps(query, **kwargs):
        seen.append(list(kwargs["history"]))
        return type("Result", (), {"answer": f"answer to {query}", "source_files": []})()

    _patch_query_path(monkeypatch, fake_run_query_with_steps)

    await chat_module._handle_query("first")
    await chat_module._handle_query("second")
    await chat_module._handle_query("third")

    # llm_history_turns = 1: each question sees only the turn before it.
    assert seen == [
        [],
        [Turn(question="first", answer="answer to first")],
        [Turn(question="second", answer="answer to second")],
    ]


@pytest.mark.asyncio
async def test_handle_query_does_not_remember_a_reply_without_an_answer(monkeypatch):
    session = _patch_session(monkeypatch)
    session.set("settings", type("Settings", (), {"llm_history_turns": 10})())
    session.set("collection", object())

    async def fake_run_query_with_steps(query, **kwargs):
        # Retrieval-only mode: the hits are shown, no answer is written.
        return type("Result", (), {"answer": None, "source_files": ["a.md"]})()

    _patch_query_path(monkeypatch, fake_run_query_with_steps)

    await chat_module._handle_query("first")

    assert session.get(chat_module.HISTORY_KEY) is None
