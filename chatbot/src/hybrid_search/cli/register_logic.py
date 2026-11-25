from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from hybrid_search import chatbot_profiles
from hybrid_search.cli.ingest_logic import INGEST_ERRORS, ingest_dirs
from hybrid_search.indexes import create_and_wait_chunks_indexes
from hybrid_search.mongo import (
    chunks_collection,
    get_client,
    ingest_state_collection,
    profiles_collection,
)
from hybrid_search.settings import HybridSearchSettings
from hybrid_search.ui.demo import load_demo_queries
from hybrid_search.ui.profiles import COLLECTION_NAME_PATTERN

logger = logging.getLogger(__name__)

REGISTER_ERRORS = (*INGEST_ERRORS, TimeoutError)


class RegisterInput(BaseModel):
    settings: HybridSearchSettings
    collection: str
    display_name: str
    description: str | None = None
    icon: str | None = None
    demo_queries_path: Path | None = None
    system_prompt_path: Path | None = None
    dirs: list[Path] = Field(default_factory=list)
    force: bool = False


class RegisterResult(BaseModel):
    exit_code: int = 0
    ready_lines: list[str] = Field(default_factory=list)
    ingested: int = 0
    skipped: int = 0


def register(input: RegisterInput) -> RegisterResult:
    return asyncio.run(_register_async(input))


async def _register_async(input: RegisterInput) -> RegisterResult:
    if not COLLECTION_NAME_PATTERN.match(input.collection):
        logger.error(
            f"invalid collection name {input.collection!r}: use letters, digits, "
            "underscores, and hyphens, starting with a letter or digit"
        )
        return RegisterResult(exit_code=1)
    # Read the input files before the index build, so a typo fails in seconds
    # instead of after several minutes of waiting for Atlas Search.
    try:
        set_fields = _set_fields(input)
    except REGISTER_ERRORS as exc:
        logger.error(f"register failed: {exc}")
        return RegisterResult(exit_code=1)
    # The command is explicit about its target, so the environment's skip flags
    # do not apply to the indexes or to an explicit --dir.
    settings = input.settings.model_copy(
        update={"chunks_collection": input.collection, "skip_index_creation": False}
    )
    client = get_client(settings)
    try:
        collection = chunks_collection(client, settings)
        ready_lines = await create_and_wait_chunks_indexes(collection, settings)
        await chatbot_profiles.upsert_profile(
            profiles_collection(client, settings),
            name=input.collection,
            set_fields=set_fields,
        )
        result = RegisterResult(ready_lines=ready_lines)
        if input.dirs:
            ingested = await ingest_dirs(
                settings,
                collection,
                ingest_state_collection(client, settings),
                input.dirs,
                force=input.force,
            )
            result = result.model_copy(
                update={"ingested": ingested.ingested, "skipped": ingested.skipped}
            )
        logger.info(
            f"Registered {input.collection} as the chat profile {input.display_name!r}. "
            "The dropdown lists it after the server's 30-second profile cache "
            "expires; reload the page."
        )
        return result
    except REGISTER_ERRORS as exc:
        logger.error(f"register failed: {exc}")
        return RegisterResult(exit_code=1)
    finally:
        client.close()


def _set_fields(input: RegisterInput) -> dict[str, object]:
    fields: dict[str, object] = {"display_name": input.display_name}
    if input.description is not None:
        fields["description"] = input.description
    if input.icon is not None:
        fields["icon"] = input.icon
    if input.demo_queries_path is not None:
        queries = load_demo_queries(input.demo_queries_path)
        fields["queries"] = [query.model_dump() for query in queries]
    if input.system_prompt_path is not None:
        prompt = input.system_prompt_path.read_text().strip()
        if not prompt:
            msg = f"system prompt file is empty: {input.system_prompt_path}"
            raise ValueError(msg)
        fields["system_prompt"] = prompt
    return fields
