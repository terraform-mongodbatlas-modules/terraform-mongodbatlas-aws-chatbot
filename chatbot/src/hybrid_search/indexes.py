from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import SearchIndexModel

from hybrid_search.health import IndexState
from hybrid_search.settings import HybridSearchSettings

IndexStatus = tuple[str, str, str]
_NAMESPACE_NOT_FOUND = 26
_BOOTSTRAP_ID = "__hybrid_search_bootstrap"
_PENDING = "PENDING"
_MISSING = "MISSING"
_FAILED = "FAILED"
logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]


def autoembed_index_definition(*, model: str) -> dict[str, Any]:
    return {
        "fields": [
            {
                "type": "autoEmbed",
                "modality": "text",
                "path": "content",
                "model": model,
            },
            {"type": "filter", "path": "file_path"},
        ]
    }


def text_index_definition() -> dict[str, Any]:
    return {
        "mappings": {
            "dynamic": False,
            "fields": {
                "content": {
                    "type": "string",
                    "analyzer": "lucene.standard",
                }
            },
        }
    }


async def _materialize_namespace(collection: AsyncIOMotorCollection) -> None:
    # Mongo only creates a database on write. createCollection is not enough for
    # Atlas Search: listSearchIndexes can return [] while createSearchIndexes
    # still raises NamespaceNotFound.
    namespace = f"{collection.database.name}.{collection.name}"
    logger.info("Atlas Search namespace missing; creating %s", namespace)
    await collection.insert_one({"_id": _BOOTSTRAP_ID})
    await collection.delete_one({"_id": _BOOTSTRAP_ID})


async def _list_search_indexes(collection: AsyncIOMotorCollection) -> list[dict[str, Any]]:
    try:
        return await collection.list_search_indexes().to_list(length=None)
    except OperationFailure as exc:
        if exc.code != _NAMESPACE_NOT_FOUND:
            raise
        await _materialize_namespace(collection)
        return await collection.list_search_indexes().to_list(length=None)


async def _create_search_index(
    collection: AsyncIOMotorCollection,
    model: SearchIndexModel,
) -> None:
    try:
        await collection.create_search_index(model)
    except OperationFailure as exc:
        if exc.code != _NAMESPACE_NOT_FOUND:
            raise
        await _materialize_namespace(collection)
        await collection.create_search_index(model)


def _index_detail(index: dict[str, Any]) -> str | None:
    raw = index.get("statusDetail")
    match raw:
        case str() as text:
            return text or None
        case list() as parts:
            messages = [
                part.get("message") if isinstance(part, dict) else str(part) for part in parts
            ]
            joined = "; ".join(message for message in messages if message)
            return joined or None
        case _:
            return None


def _index_state(name: str, index: dict[str, Any] | None) -> IndexState:
    if index is None:
        return IndexState(name=name, status=_MISSING)
    return IndexState(
        name=name,
        status=index.get("status") or _MISSING,
        detail=_index_detail(index),
    )


async def create_chunks_indexes_if_missing(
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
    *,
    recreate_failed: bool = False,
) -> None:
    existing = {
        index.get("name"): index
        for index in await _list_search_indexes(collection)
        if index.get("name")
    }
    definitions = [
        (
            settings.vector_index_name,
            SearchIndexModel(
                definition=autoembed_index_definition(model=settings.autoembed_model),
                name=settings.vector_index_name,
                type="vectorSearch",
            ),
        ),
        (
            settings.text_index_name,
            SearchIndexModel(
                definition=text_index_definition(),
                name=settings.text_index_name,
                type="search",
            ),
        ),
    ]
    for name, model in definitions:
        index = existing.get(name)
        # Atlas keeps a failed build under the same name, so skipping every
        # existing name would leave it broken on each restart.
        if index is not None and recreate_failed and index.get("status") == _FAILED:
            logger.warning(f"dropping FAILED index {collection.name}.{name} before recreating it")
            await collection.drop_search_index(name)
            index = None
        if index is None:
            await _create_search_index(collection, model)


async def _create_with_retry(
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
    *,
    recreate_failed: bool,
    attempts: int,
    base_delay_s: float,
    max_delay_s: float,
    sleep: Sleep,
) -> None:
    for attempt in range(attempts):
        try:
            await create_chunks_indexes_if_missing(
                collection,
                settings,
                recreate_failed=recreate_failed,
            )
            return
        except PyMongoError as exc:
            if attempt + 1 >= attempts:
                raise
            delay = min(max_delay_s, base_delay_s * 2**attempt)
            logger.warning(
                f"index creation attempt {attempt + 1} of {attempts} failed: {exc}; "
                f"retrying in {delay:.0f}s"
            )
            await sleep(delay)


async def create_and_wait_chunks_indexes(
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
    *,
    recreate_failed: bool = False,
    create_attempts: int = 1,
    base_delay_s: float = 2.0,
    max_delay_s: float = 30.0,
    sleep: Sleep = asyncio.sleep,
) -> list[str]:
    """Create the missing chunks indexes, wait for READY, and log each one."""
    await _create_with_retry(
        collection,
        settings,
        recreate_failed=recreate_failed,
        attempts=create_attempts,
        base_delay_s=base_delay_s,
        max_delay_s=max_delay_s,
        sleep=sleep,
    )
    ready = await wait_chunks_indexes_ready(collection, settings)
    lines = [
        format_index_ready_line(collection_name, index_name)
        for collection_name, index_name, _status in ready
    ]
    for line in lines:
        logger.info(line)
    return lines


async def index_states(
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
) -> list[IndexState]:
    by_name = {
        index.get("name"): index
        for index in await _list_search_indexes(collection)
        if index.get("name")
    }
    return [
        _index_state(name, by_name.get(name))
        for name in (settings.vector_index_name, settings.text_index_name)
    ]


async def ensure_indexes_ready(
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
) -> None:
    states = await index_states(collection, settings)
    not_ready = [state for state in states if state.status != "READY"]
    if not not_ready:
        return
    detail = ", ".join(f"{state.name} ({state.status})" for state in not_ready)
    msg = f"search indexes are not ready on {collection.name}: {detail}"
    raise RuntimeError(msg)


async def wait_chunks_indexes_ready(
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
    *,
    timeout_s: int = 600,
    interval_s: int = 10,
) -> list[IndexStatus]:
    names = {settings.vector_index_name, settings.text_index_name}
    deadline = time.monotonic() + timeout_s
    ready: list[IndexStatus] = []
    seen_ready: set[str] = set()
    while time.monotonic() < deadline:
        indexes = await _list_search_indexes(collection)
        by_name = {index.get("name"): index for index in indexes if index.get("name")}
        for name in names:
            index = by_name.get(name)
            status = index.get("status") if index else _PENDING
            logger.info(f"{settings.chunks_collection}.{name} {status}")
            if status == _FAILED:
                detail = _index_detail(index) if index else None
                msg = f"index {settings.chunks_collection}.{name} failed"
                if detail:
                    msg = f"{msg}: {detail}"
                raise RuntimeError(msg)
            if status == "READY" and name not in seen_ready:
                seen_ready.add(name)
                ready.append((settings.chunks_collection, name, status))
        if seen_ready == names:
            return ready
        await asyncio.sleep(interval_s)
    msg = f"timed out waiting for indexes on {settings.chunks_collection}"
    raise TimeoutError(msg)


def format_index_ready_line(collection: str, index_name: str) -> str:
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{date} {collection}.{index_name} READY"
