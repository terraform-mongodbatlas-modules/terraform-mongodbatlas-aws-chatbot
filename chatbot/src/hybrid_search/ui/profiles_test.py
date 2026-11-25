from __future__ import annotations

import pytest
from pydantic import SecretStr
from pymongo.errors import OperationFailure

import hybrid_search.ui.profiles as profiles_module
from hybrid_search.chatbot_profiles import PROFILES_COLLECTION, DemoQuery
from hybrid_search.settings import HybridSearchSettings
from hybrid_search.ui.profiles import (
    COLLECTION_SCOPED_GRANT_MESSAGE,
    CollectionProfile,
    ProfileListing,
    clear_profile_cache,
    list_profiles,
    load_profile_listing,
    rejected_profile_message,
    resolve_profile,
)

DB_NAME = "hybrid_search"


class _FakeCursor:
    def __init__(self, registry: _FakeRegistry) -> None:
        self._registry = registry

    async def to_list(self, length: object) -> list[dict]:
        self._registry.find_calls += 1
        if self._registry.unauthorized:
            raise OperationFailure("not authorized on _chatbot_profiles", code=13)
        return [
            {"_id": name, **doc} for name, doc in self._registry.docs.items() if doc is not None
        ]


class _FakeRegistry:
    name = PROFILES_COLLECTION

    def __init__(self, docs: dict[str, dict | None], *, unauthorized: bool = False) -> None:
        self.docs = docs
        self.unauthorized = unauthorized
        self.find_calls = 0

    def find(self, filter: dict) -> _FakeCursor:
        assert filter == {}
        return _FakeCursor(self)


class _FakeDatabase:
    def __init__(self, docs: dict[str, dict | None], *, unauthorized: bool = False) -> None:
        self.registry = _FakeRegistry(docs, unauthorized=unauthorized)

    def __getitem__(self, name: str) -> _FakeRegistry:
        assert name == PROFILES_COLLECTION
        return self.registry


class _FakeClient:
    def __init__(self, database: _FakeDatabase) -> None:
        self._database = database
        self.closed = False

    def __getitem__(self, name: str) -> _FakeDatabase:
        assert name == DB_NAME
        return self._database

    def close(self) -> None:
        self.closed = True


LISTING = ProfileListing(
    profiles=[
        CollectionProfile(collection="chunks", display_name="chunks", default=True),
        CollectionProfile(
            collection="health",
            display_name="Healthcare",
            description="Clinical notes",
            icon="hospital",
        ),
    ]
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_profile_cache()
    yield
    clear_profile_cache()


def _settings(chunks_collection: str = "chunks") -> HybridSearchSettings:
    return HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        mongodb_database=DB_NAME,
        chunks_collection=chunks_collection,
    )


def _profile(display_name: str, **extra: object) -> dict:
    return {"display_name": display_name, **extra}


@pytest.mark.parametrize(
    ("docs", "expected"),
    [
        ({}, [("chunks", "chunks", True)]),
        (
            {"health": _profile("Healthcare")},
            [("chunks", "chunks", True), ("health", "Healthcare", False)],
        ),
        (
            {"chunks": _profile("Docs"), "health": _profile("Healthcare")},
            [("chunks", "Docs", True), ("health", "Healthcare", False)],
        ),
        # A registry entry with an invalid collection name never becomes a profile.
        ({"bad.name": _profile("Bad")}, [("chunks", "chunks", True)]),
        # The app owns the `*_ingest_state` suffix, so an entry there is not a corpus.
        ({"chunks_ingest_state": _profile("State")}, [("chunks", "chunks", True)]),
        # A registry entry without a usable label is not a registration.
        ({"health": _profile("")}, [("chunks", "chunks", True)]),
    ],
)
async def test_list_profiles(docs: dict, expected: list[tuple[str, str, bool]]):
    listing = await list_profiles(_FakeDatabase(docs), default_collection="chunks")

    assert [
        (profile.collection, profile.display_name, profile.default) for profile in listing.profiles
    ] == expected
    assert listing.auth_limited is False


async def test_list_profiles_sorts_other_profiles_by_label():
    docs = {"zeta": _profile("Alpha"), "beta": _profile("Zulu")}

    listing = await list_profiles(_FakeDatabase(docs), default_collection="chunks")

    assert [profile.collection for profile in listing.profiles] == ["chunks", "zeta", "beta"]


async def test_list_profiles_carries_the_registry_fields():
    docs = {
        "health": _profile(
            "Healthcare",
            description="Clinical notes",
            icon="hospital",
            queries=[{"label": "Marge", "message": "What is due?"}],
            system_prompt="Answer as the member assistant.",
        ),
    }

    listing = await list_profiles(_FakeDatabase(docs), default_collection="chunks")

    health = listing.by_collection()["health"]
    assert health.description == "Clinical notes"
    assert health.icon == "hospital"
    assert health.queries == (DemoQuery(label="Marge", message="What is due?"),)
    assert health.system_prompt == "Answer as the member assistant."


async def test_list_profiles_reports_an_auth_limited_registry():
    database = _FakeDatabase({"chunks": _profile("Docs")}, unauthorized=True)

    listing = await list_profiles(database, default_collection="chunks")

    assert listing.auth_limited is True
    assert [profile.collection for profile in listing.profiles] == ["chunks"]
    assert listing.default.display_name == "chunks"


async def test_load_profile_listing_caches_within_the_ttl():
    database = _FakeDatabase({"health": _profile("Healthcare")})
    client = _FakeClient(database)
    now = [100.0]

    first = await load_profile_listing(_settings(), client=client, clock=lambda: now[0])
    now[0] += profiles_module.PROFILE_CACHE_TTL_S - 1
    second = await load_profile_listing(_settings(), client=client, clock=lambda: now[0])

    assert second == first
    assert database.registry.find_calls == 1
    assert client.closed is False


async def test_load_profile_listing_refreshes_after_the_ttl():
    database = _FakeDatabase({})
    client = _FakeClient(database)
    now = [100.0]

    await load_profile_listing(_settings(), client=client, clock=lambda: now[0])
    now[0] += profiles_module.PROFILE_CACHE_TTL_S + 1
    await load_profile_listing(_settings(), client=client, clock=lambda: now[0])

    assert database.registry.find_calls == 2


async def test_load_profile_listing_caches_per_chunks_collection():
    database = _FakeDatabase({"health": _profile("Healthcare")})
    client = _FakeClient(database)

    await load_profile_listing(_settings("chunks"), client=client)
    await load_profile_listing(_settings("health"), client=client)

    assert database.registry.find_calls == 2


async def test_load_profile_listing_closes_a_client_it_opens(monkeypatch):
    database = _FakeDatabase({})
    client = _FakeClient(database)
    monkeypatch.setattr(profiles_module, "get_client", lambda _settings: client)

    await load_profile_listing(_settings())

    assert client.closed is True


@pytest.mark.parametrize(
    ("name", "expected_collection", "expected_rejected"),
    [
        (None, "chunks", None),
        ("", "chunks", None),
        ("chunks", "chunks", None),
        ("health", "health", None),
        ("unknown", "chunks", "unknown"),
        ("bad.name", "chunks", "bad.name"),
        ("-leading", "chunks", "-leading"),
        ("a" * 121, "chunks", "a" * 121),
    ],
)
def test_resolve_profile(name: str | None, expected_collection: str, expected_rejected: str | None):
    resolution = resolve_profile(name, LISTING)

    assert resolution.profile.collection == expected_collection
    assert resolution.rejected_name == expected_rejected


def test_rejected_profile_message_names_the_value_and_the_fallback():
    resolution = resolve_profile("unknown", LISTING)

    message = rejected_profile_message(resolution)

    assert '"unknown"' in message
    assert '"chunks"' in message


def test_collection_scoped_grant_message_names_the_module_input():
    assert "db_access.collection_name" in COLLECTION_SCOPED_GRANT_MESSAGE
