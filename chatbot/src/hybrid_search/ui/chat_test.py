from __future__ import annotations

import pytest

import hybrid_search.ui.chat as chat_module
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
