from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from hybrid_search.indexes import create_and_wait_chunks_indexes
from hybrid_search.mongo import chunks_collection, get_client
from hybrid_search.settings import HybridSearchSettings

logger = logging.getLogger(__name__)


class IndexCreateInput(BaseModel):
    settings: HybridSearchSettings
    recreate: bool = False


class IndexCreateResult(BaseModel):
    exit_code: int = 0
    ready_lines: list[str] = Field(default_factory=list)
    error: str | None = None


def index_create(input: IndexCreateInput) -> IndexCreateResult:
    return asyncio.run(_index_create_async(input))


async def _index_create_async(input: IndexCreateInput) -> IndexCreateResult:
    settings = input.settings
    client = get_client(settings)
    try:
        collection = chunks_collection(client, settings)
        lines = await create_and_wait_chunks_indexes(
            collection,
            settings,
            recreate_failed=input.recreate,
            create_attempts=3,
        )
        return IndexCreateResult(ready_lines=lines)
    except (TimeoutError, RuntimeError, PyMongoError) as exc:
        logger.error(f"index create failed: {exc}")
        return IndexCreateResult(exit_code=1, error=str(exc))
    finally:
        client.close()
