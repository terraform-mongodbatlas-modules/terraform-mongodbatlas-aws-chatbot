"""The profile registry: one document per selectable chunks collection.

The registry lives in the ``_chatbot_profiles`` collection in
``MONGODB_DATABASE``, so a chunks collection holds only chunks and no read or
delete path needs to exclude metadata. A document's ``_id`` is the chunks
collection name; its presence is the allowlist the chat profile dropdown
renders.

The document carries the label, the demo queries, and the system prompt for that
corpus, so a registered collection describes itself instead of inheriting the
image's bundled values. The leading underscore in the collection name keeps a
client-supplied profile name from ever selecting the registry itself, because
``COLLECTION_NAME_PATTERN`` rejects a leading underscore.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pymongo.errors import PyMongoError

PROFILES_COLLECTION = "_chatbot_profiles"

logger = logging.getLogger(__name__)


class DemoQuery(BaseModel):
    label: str
    message: str


class DemoQueriesFile(BaseModel):
    queries: list[DemoQuery] = Field(min_length=1)


class ChatbotProfile(BaseModel):
    """The stored profile document; ``_id``, the collection name, is the key."""

    model_config = ConfigDict(extra="ignore")

    display_name: str = Field(min_length=1)
    description: str | None = None
    icon: str | None = None
    queries: list[DemoQuery] = Field(default_factory=list)
    system_prompt: str | None = None

    @field_validator("queries", mode="before")
    @classmethod
    def empty_for_null_queries(cls, value: object) -> object:
        # A hand-written ``queries:`` line parses as null. Treat it as no chips
        # instead of dropping the whole registration from the dropdown.
        return [] if value is None else value


class StartupStatus(BaseModel):
    """The last startup task outcome, stored beside the profile fields."""

    outcome: Literal["ok", "failed"]
    phase: str
    error: str | None = None
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


async def load_registry(
    collection: AsyncIOMotorCollection,
) -> dict[str, ChatbotProfile]:
    profiles: dict[str, ChatbotProfile] = {}
    for doc in await collection.find({}).to_list(length=None):
        name = doc.get("_id")
        if not isinstance(name, str):
            continue
        if profile := _validated(collection, doc):
            profiles[name] = profile
    return profiles


def _validated(
    collection: AsyncIOMotorCollection,
    doc: Mapping[str, Any],
) -> ChatbotProfile | None:
    try:
        return ChatbotProfile.model_validate(doc)
    except ValidationError:
        logger.warning(
            f"Ignoring profile {doc.get('_id')!r} in {collection.name}: "
            "not a ChatbotProfile document"
        )
        return None


async def upsert_profile(
    collection: AsyncIOMotorCollection,
    *,
    name: str,
    set_fields: Mapping[str, Any],
    insert_fields: Mapping[str, Any] | None = None,
) -> None:
    """Create or update the profile for ``name``.

    ``insert_fields`` apply only when the document is created, so a label a
    caller registered survives a restart. Mongo rejects a field that appears in
    both ``set_fields`` and ``insert_fields``.
    """
    update: dict[str, Any] = {"$set": dict(set_fields)}
    if insert_fields:
        update["$setOnInsert"] = dict(insert_fields)
    await collection.update_one({"_id": name}, update, upsert=True)


async def record_startup_status(
    collection: AsyncIOMotorCollection,
    *,
    name: str,
    status: StartupStatus,
) -> None:
    """Write the last startup outcome beside the profile fields.

    ``upsert=False`` on purpose: a status write must never create a document
    without ``display_name``, which would drop the default profile from the
    listing. The startup task writes the profile first, so the document exists.
    """
    await collection.update_one(
        {"_id": name},
        {"$set": {"startup": status.model_dump()}},
        upsert=False,
    )


async def load_startup_status(
    collection: AsyncIOMotorCollection,
    *,
    name: str,
) -> StartupStatus | None:
    try:
        doc = await collection.find_one({"_id": name})
    except PyMongoError as exc:
        logger.warning(f"could not read startup status for {name!r}: {exc}")
        return None
    if not doc or doc.get("startup") is None:
        return None
    try:
        return StartupStatus.model_validate(doc["startup"])
    except ValidationError:
        logger.warning(f"Ignoring the startup status on {name!r}: not a StartupStatus document")
        return None
