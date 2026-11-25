from __future__ import annotations

import pytest
from pydantic import SecretStr

import hybrid_search.ui.chat as chat_module
from hybrid_search.chatbot_profiles import DemoQuery, StartupStatus
from hybrid_search.ingest import IngestedFile
from hybrid_search.settings import DEFAULT_RAG_SYSTEM_PROMPT, HybridSearchSettings
from hybrid_search.ui.demo import Mode
from hybrid_search.ui.profiles import CollectionProfile, ProfileListing


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
    session.set("settings", HybridSearchSettings(mongodb_uri=SecretStr("mongodb://localhost")))
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
    monkeypatch.setattr(chat_module, "problem_message", lambda states, query, collection: None)
    monkeypatch.setattr(chat_module, "run_query_with_steps", fake_run_query_with_steps)
    monkeypatch.setattr(chat_module.cl, "Message", _FakeMessage)

    await chat_module._handle_query("risk")

    assert sent == ["Query failed: Unable to locate credentials"]


DEFAULT_PROFILE = CollectionProfile(collection="chunks", display_name="chunks", default=True)
HEALTH_PROFILE = CollectionProfile(
    collection="health",
    display_name="Healthcare",
    description="Clinical notes",
    icon="hospital",
)
LISTING = ProfileListing(profiles=[DEFAULT_PROFILE, HEALTH_PROFILE])


class _FakeCollection:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeDatabase:
    def __getitem__(self, name: str) -> _FakeCollection:
        return _FakeCollection(name)


class _FakeClient:
    def __init__(self) -> None:
        self.closed = False

    def __getitem__(self, name: str) -> _FakeDatabase:
        return _FakeDatabase()

    def close(self) -> None:
        self.closed = True


class _FakeEmitter:
    async def set_commands(self, commands: object) -> None:
        return None


class _FakeContext:
    emitter = _FakeEmitter()


def _patch_startup(
    monkeypatch,
    *,
    listing: ProfileListing,
) -> tuple[_FakeSession, list[str]]:
    session = _patch_session(monkeypatch)
    sent: list[str] = []
    settings = HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        mongodb_database="hybrid_search",
        chunks_collection="chunks",
    )

    class _FakeMessage:
        def __init__(self, content: str = "") -> None:
            self.content = content

        async def send(self) -> None:
            sent.append(self.content)

    async def fake_listing(*args: object, **kwargs: object) -> ProfileListing:
        return listing

    async def fake_index_states(collection: object, settings: object) -> list:
        return []

    async def fake_load_startup_status(collection: object, *, name: str) -> None:
        return None

    async def fake_send_default_settings() -> None:
        return None

    monkeypatch.setattr(chat_module, "get_settings", lambda: settings)
    monkeypatch.setattr(chat_module, "get_client", lambda _settings: _FakeClient())
    monkeypatch.setattr(chat_module, "load_profile_listing", fake_listing)
    monkeypatch.setattr(chat_module, "load_demo_queries", lambda path: [])
    monkeypatch.setattr(chat_module, "apply_log_level", lambda level: None)
    monkeypatch.setattr(chat_module, "index_states", fake_index_states)
    monkeypatch.setattr(chat_module, "load_startup_status", fake_load_startup_status)
    monkeypatch.setattr(
        chat_module, "problem_message", lambda states, query, collection, startup=None: None
    )
    monkeypatch.setattr(chat_module, "send_default_settings", fake_send_default_settings)
    monkeypatch.setattr(chat_module.cl, "Message", _FakeMessage)
    monkeypatch.setattr(chat_module.cl, "context", _FakeContext())
    return session, sent


@pytest.mark.asyncio
async def test_on_chat_start_uses_the_selected_profile(monkeypatch):
    session, sent = _patch_startup(monkeypatch, listing=LISTING)
    session.set("chat_profile", "health")

    await chat_module.on_chat_start()

    session_settings = session.get("settings")
    assert session_settings.chunks_collection == "health"
    assert session.get("collection").name == "health"
    assert session.get("state_collection").name == "health_ingest_state"
    assert sent == []


@pytest.mark.asyncio
async def test_on_chat_start_passes_the_recorded_startup_status(monkeypatch):
    session, _sent = _patch_startup(monkeypatch, listing=LISTING)
    session.set("chat_profile", "health")
    startup = StartupStatus(outcome="failed", phase="indexes", error="model is not enabled")
    seen: list[StartupStatus | None] = []

    async def fake_load_startup_status(collection: object, *, name: str) -> StartupStatus:
        return startup

    def fake_problem_message(states, *, query, collection, startup=None):
        seen.append(startup)

    monkeypatch.setattr(chat_module, "load_startup_status", fake_load_startup_status)
    monkeypatch.setattr(chat_module, "problem_message", fake_problem_message)

    await chat_module.on_chat_start()

    assert seen == [startup]


@pytest.mark.asyncio
async def test_on_chat_start_falls_back_and_names_the_rejected_profile(monkeypatch):
    session, sent = _patch_startup(monkeypatch, listing=LISTING)
    session.set("chat_profile", "nope")

    await chat_module.on_chat_start()

    session_settings = session.get("settings")
    assert session_settings.chunks_collection == "chunks"
    assert any('"nope"' in content for content in sent)


@pytest.mark.asyncio
async def test_on_chat_start_explains_a_collection_scoped_grant(monkeypatch):
    listing = ProfileListing(profiles=[DEFAULT_PROFILE], auth_limited=True)
    _session, sent = _patch_startup(monkeypatch, listing=listing)

    await chat_module.on_chat_start()

    assert any("db_access.collection_name" in content for content in sent)


@pytest.mark.asyncio
async def test_set_chat_profiles_maps_the_listing_to_chainlit_profiles(monkeypatch):
    _session, _sent = _patch_startup(monkeypatch, listing=LISTING)

    profiles = await chat_module.set_chat_profiles()

    assert [(profile.name, profile.default) for profile in profiles] == [
        ("chunks", True),
        ("health", False),
    ]
    assert profiles[1].markdown_description == "Clinical notes"
    assert profiles[1].icon == "hospital"


PROFILE_QUERIES = (DemoQuery(label="Marge", message="What is due?"),)
_DEMO_ASKS: list[list] = []


@pytest.mark.asyncio
async def test_set_chat_profiles_uses_the_document_label_and_starters(monkeypatch):
    listing = ProfileListing(
        profiles=[
            CollectionProfile(
                collection="chunks",
                display_name="Product docs",
                queries=PROFILE_QUERIES,
                default=True,
            ),
            CollectionProfile(
                collection="health",
                display_name="Healthcare",
                queries=PROFILE_QUERIES,
            ),
        ]
    )
    _patch_startup(monkeypatch, listing=listing)

    profiles = await chat_module.set_chat_profiles()

    assert [profile.display_name for profile in profiles] == ["Product docs", "Healthcare"]
    assert [starter.label for starter in profiles[1].starters[:2]] == [
        "Upload documents",
        "Delete documents",
    ]
    assert profiles[1].starters[-1].label == "Marge"


@pytest.mark.asyncio
async def test_set_chat_profiles_falls_back_to_the_bundled_queries_for_the_default(monkeypatch):
    _patch_startup(monkeypatch, listing=LISTING)
    monkeypatch.setattr(
        chat_module,
        "load_demo_queries",
        lambda path: [DemoQuery(label="Bundled", message="What is bundled?")],
    )

    profiles = await chat_module.set_chat_profiles()

    assert profiles[0].starters[-1].label == "Bundled"
    # A registered profile without queries gets only the upload and delete chips.
    assert [starter.label for starter in profiles[1].starters] == [
        "Upload documents",
        "Delete documents",
    ]


@pytest.mark.asyncio
async def test_on_chat_start_uses_the_profiles_system_prompt(monkeypatch):
    listing = ProfileListing(
        profiles=[
            DEFAULT_PROFILE,
            CollectionProfile(
                collection="health",
                display_name="Healthcare",
                system_prompt="Answer as Springfield Health.",
            ),
        ]
    )
    session, _sent = _patch_startup(monkeypatch, listing=listing)
    session.set("chat_profile", "health")

    await chat_module.on_chat_start()

    assert session.get("settings").rag_system_prompt == "Answer as Springfield Health."


@pytest.mark.asyncio
async def test_on_chat_start_keeps_the_env_system_prompt_when_the_profile_has_none(monkeypatch):
    session, _sent = _patch_startup(monkeypatch, listing=LISTING)
    session.set("chat_profile", "health")

    await chat_module.on_chat_start()

    assert session.get("settings").rag_system_prompt == DEFAULT_RAG_SYSTEM_PROMPT


class _FakeAskActionMessage:
    def __init__(self, content: str, actions: list, timeout: int, raise_on_timeout: bool) -> None:
        _DEMO_ASKS.append(actions)

    async def send(self) -> None:
        return None

    async def remove(self) -> None:
        return None


def _stub_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_module,
        "get_settings",
        lambda: HybridSearchSettings(mongodb_uri=SecretStr("mongodb://localhost")),
    )


@pytest.mark.parametrize(
    ("profile", "expected_labels"),
    [
        (
            CollectionProfile(
                collection="health",
                display_name="Healthcare",
                queries=(DemoQuery(label="Marge", message="What is due?"),),
            ),
            ["Marge", "Cancel"],
        ),
        (CollectionProfile(collection="health", display_name="Healthcare"), ["Bundled", "Cancel"]),
        (None, ["Bundled", "Cancel"]),
    ],
)
@pytest.mark.asyncio
async def test_show_demo_questions_uses_the_selected_profiles_queries(
    monkeypatch,
    profile: CollectionProfile | None,
    expected_labels: list[str],
):
    session = _patch_session(monkeypatch)
    session.set("profile", profile)
    _DEMO_ASKS.clear()
    _stub_settings(monkeypatch)
    monkeypatch.setattr(
        chat_module,
        "load_demo_queries",
        lambda path: [DemoQuery(label="Bundled", message="What is bundled?")],
    )
    monkeypatch.setattr(chat_module.cl, "AskActionMessage", _FakeAskActionMessage)

    await chat_module._show_demo_questions()

    assert [action.label for action in _DEMO_ASKS[0]] == expected_labels
