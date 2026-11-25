from __future__ import annotations

import pytest

from hybrid_search.chatbot_profiles import (
    PROFILES_COLLECTION,
    ChatbotProfile,
    DemoQuery,
    load_registry,
    upsert_profile,
)


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    async def to_list(self, length: object) -> list[dict]:
        return self._docs


class _FakeCollection:
    name = PROFILES_COLLECTION

    def __init__(self, docs: list[dict] | None = None) -> None:
        self._docs = docs or []
        self.updates: list[dict] = []

    def find(self, filter: dict) -> _FakeCursor:
        assert filter == {}
        return _FakeCursor(self._docs)

    async def update_one(self, filter: dict, update: dict, upsert: bool = False) -> None:
        self.updates.append({"filter": filter, "update": update, "upsert": upsert})


def _doc(name: str = "healthcare", **overrides: object) -> dict:
    base: dict[str, object] = {"_id": name, "display_name": "Healthcare"}
    base.update(overrides)
    return base


async def test_load_registry_parses_queries_and_the_prompt():
    doc = _doc(
        queries=[{"label": "Marge", "message": "What is due?"}],
        system_prompt="Answer as the member assistant.",
    )

    registry = await load_registry(_FakeCollection([doc]))

    assert registry["healthcare"] == ChatbotProfile(
        display_name="Healthcare",
        queries=[DemoQuery(label="Marge", message="What is due?")],
        system_prompt="Answer as the member assistant.",
    )


async def test_load_registry_defaults_to_no_queries_and_no_prompt():
    registry = await load_registry(_FakeCollection([_doc()]))

    assert registry["healthcare"].queries == []
    assert registry["healthcare"].system_prompt is None


async def test_load_registry_treats_null_queries_as_empty():
    registry = await load_registry(_FakeCollection([_doc(queries=None)]))

    assert registry["healthcare"].queries == []


async def test_load_registry_ignores_unknown_fields():
    registry = await load_registry(_FakeCollection([_doc(unexpected="not a profile field")]))

    assert registry["healthcare"].display_name == "Healthcare"


@pytest.mark.parametrize(
    "doc",
    [
        {"display_name": "No id"},
        {"_id": 7, "display_name": "Not a string"},
        _doc(display_name=None),
        _doc(display_name=""),
    ],
)
async def test_load_registry_skips_a_document_without_a_usable_name_or_label(doc: dict):
    assert await load_registry(_FakeCollection([doc])) == {}


@pytest.mark.parametrize(
    ("insert_fields", "expected_update"),
    [
        (
            {"display_name": "chunks"},
            {
                "$set": {"system_prompt": "Answer briefly."},
                "$setOnInsert": {"display_name": "chunks"},
            },
        ),
        (
            None,
            {"$set": {"system_prompt": "Answer briefly."}},
        ),
    ],
)
async def test_upsert_profile_keys_the_document_by_collection_name(
    insert_fields: dict | None,
    expected_update: dict,
):
    collection = _FakeCollection()

    await upsert_profile(
        collection,
        name="healthcare",
        set_fields={"system_prompt": "Answer briefly."},
        insert_fields=insert_fields,
    )

    assert collection.updates == [
        {"filter": {"_id": "healthcare"}, "update": expected_update, "upsert": True}
    ]
