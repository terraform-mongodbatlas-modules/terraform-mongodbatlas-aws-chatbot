from __future__ import annotations

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from hybrid_search.chatbot_profiles import PROFILES_COLLECTION
from hybrid_search.settings import HybridSearchSettings

INGEST_STATE_SUFFIX = "_ingest_state"


def ingest_state_collection_name(chunks_collection: str) -> str:
    # One state collection per chunks collection: two profiles in one database
    # must not share content hashes and skip each other's files.
    return f"{chunks_collection}{INGEST_STATE_SUFFIX}"


def get_client(
    settings: HybridSearchSettings,
    *,
    server_selection_timeout_ms: int | None = None,
    tls: bool | None = None,
) -> AsyncIOMotorClient:
    timeout_ms = server_selection_timeout_ms or settings.mongo_server_selection_timeout_ms
    use_tls = settings.mongodb_tls if tls is None else tls
    tls_kwargs = {"tlsCAFile": certifi.where()} if use_tls else {"tls": False}
    return AsyncIOMotorClient(
        settings.mongodb_uri.get_secret_value(),
        serverSelectionTimeoutMS=timeout_ms,
        **tls_kwargs,
    )


def chunks_collection(
    client: AsyncIOMotorClient,
    settings: HybridSearchSettings,
) -> AsyncIOMotorCollection:
    return client[settings.mongodb_database][settings.chunks_collection]


def ingest_state_collection(
    client: AsyncIOMotorClient,
    settings: HybridSearchSettings,
) -> AsyncIOMotorCollection:
    name = ingest_state_collection_name(settings.chunks_collection)
    return client[settings.mongodb_database][name]


def profiles_collection(
    client: AsyncIOMotorClient,
    settings: HybridSearchSettings,
) -> AsyncIOMotorCollection:
    return client[settings.mongodb_database][PROFILES_COLLECTION]
