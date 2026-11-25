from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

from hybrid_search.indexes import create_and_wait_chunks_indexes
from hybrid_search.mongo import chunks_collection, get_client
from hybrid_search.settings import HybridSearchSettings

logger = logging.getLogger(__name__)


class IndexCreateInput(BaseModel):
    settings: HybridSearchSettings


class IndexCreateResult(BaseModel):
    exit_code: int = 0
    ready_lines: list[str] = Field(default_factory=list)


def index_create(input: IndexCreateInput) -> IndexCreateResult:
    return asyncio.run(_index_create_async(input))


async def _index_create_async(input: IndexCreateInput) -> IndexCreateResult:
    settings = input.settings
    client = get_client(settings)
    try:
        collection = chunks_collection(client, settings)
        lines = await create_and_wait_chunks_indexes(collection, settings)
        return IndexCreateResult(ready_lines=lines)
    except (TimeoutError, RuntimeError) as exc:
        logger.error(f"index create failed: {exc}")
        return IndexCreateResult(exit_code=1)
    finally:
        client.close()
