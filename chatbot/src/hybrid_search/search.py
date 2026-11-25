from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from hybrid_search.search_modes import SearchModes
from hybrid_search.settings import HybridSearchSettings


class RetrievalPipeline(StrEnum):
    KEYWORD = "keyword"
    VECTOR = "vector"
    RANK_FUSION = "rank_fusion"


@dataclass(frozen=True)
class SearchResult:
    references: list[dict[str, Any]]
    pipeline: RetrievalPipeline
    # True when $rerank reordered the candidates; the scores are then rerank scores.
    reranked: bool = False


# $rankFusion pipeline adapted from Hybrid-Search-RAG (Apache-2.0).
# numCandidates: Atlas recommends at least 20x limit for ANN recall.
# https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/
NUM_CANDIDATES_MULTIPLIER = 20
# maxEdits accepts 1 or 2; prefixLength defaults to 0.
# https://www.mongodb.com/docs/search/query/operators-collectors/text
FUZZY_MAX_EDITS = 2
FUZZY_PREFIX_LENGTH = 3
VECTOR_PATH = "content"
TEXT_PATH = "content"
# Atlas caps numCandidates.
# https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/
MAX_NUM_CANDIDATES = 10_000


def _rerank_stages(query_text: str, *, settings: HybridSearchSettings) -> list[dict[str, Any]]:
    # Retrieval finds the candidates, $rerank orders them: it reads the question
    # against each candidate's text and returns them best first, so the stages
    # before it only decide which documents it gets to see.
    # https://www.mongodb.com/docs/vector-search/query/aggregation-stages/rerank/
    return [
        # $rerank fails on a document without the path field.
        {"$match": {TEXT_PATH: {"$type": "string"}}},
        {
            "$rerank": {
                "model": settings.rerank_model,
                "query": {"text": query_text},
                "path": TEXT_PATH,
                "numDocsToRerank": settings.rerank_candidates,
            }
        },
        {"$addFields": {"hybrid_score": {"$meta": "score"}}},
        {"$limit": settings.top_k},
    ]


def _text_search_stages(
    query_text: str,
    *,
    text_index_name: str,
    limit: int,
) -> list[dict[str, Any]]:
    return [
        {
            "$search": {
                "index": text_index_name,
                "compound": {
                    "must": [
                        {
                            "text": {
                                "query": query_text,
                                "path": TEXT_PATH,
                                "fuzzy": {
                                    "maxEdits": FUZZY_MAX_EDITS,
                                    "prefixLength": FUZZY_PREFIX_LENGTH,
                                },
                            }
                        }
                    ]
                },
            }
        },
        {"$limit": limit},
    ]


def build_text_search_pipeline(
    query_text: str,
    *,
    settings: HybridSearchSettings,
    rerank: bool = False,
) -> list[dict[str, Any]]:
    if rerank:
        return [
            *_text_search_stages(
                query_text,
                text_index_name=settings.text_index_name,
                limit=settings.rerank_candidates,
            ),
            *_rerank_stages(query_text, settings=settings),
            {"$project": {"vector": 0}},
        ]
    return [
        *_text_search_stages(
            query_text,
            text_index_name=settings.text_index_name,
            limit=settings.top_k,
        ),
        {"$addFields": {"hybrid_score": {"$meta": "searchScore"}}},
        {"$project": {"vector": 0}},
    ]


def build_vector_search_pipeline(
    query_text: str,
    *,
    settings: HybridSearchSettings,
    rerank: bool = False,
) -> list[dict[str, Any]]:
    # With a rerank, the search returns the candidates and $rerank cuts to top_k.
    limit = settings.rerank_candidates if rerank else settings.top_k
    search = [
        {
            "$vectorSearch": {
                "index": settings.vector_index_name,
                "path": VECTOR_PATH,
                "query": {"text": query_text},
                "numCandidates": min(limit * NUM_CANDIDATES_MULTIPLIER, MAX_NUM_CANDIDATES),
                "limit": limit,
            }
        },
        {"$limit": limit},
    ]
    if rerank:
        return [
            *search,
            *_rerank_stages(query_text, settings=settings),
            {"$project": {"vector": 0}},
        ]
    return [
        *search,
        {"$addFields": {"hybrid_score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"vector": 0}},
    ]


def build_rank_fusion_pipeline(
    query_text: str,
    *,
    settings: HybridSearchSettings,
    rerank: bool = False,
) -> list[dict[str, Any]]:
    top_k = settings.top_k
    inner_limit = top_k * 2
    if rerank:
        # Each half supplies at least half of the candidates the reranker reads.
        inner_limit = max(inner_limit, -(-settings.rerank_candidates // 2))
    # Unchanged without a rerank: 20 x top_k candidates for a limit of 2 x top_k.
    num_candidates = min(inner_limit * NUM_CANDIDATES_MULTIPLIER // 2, MAX_NUM_CANDIDATES)
    vector_pipeline = [
        {
            "$vectorSearch": {
                "index": settings.vector_index_name,
                "path": VECTOR_PATH,
                "query": {"text": query_text},
                "numCandidates": num_candidates,
                "limit": inner_limit,
            }
        },
        {"$limit": inner_limit},
    ]
    text_pipeline = _text_search_stages(
        query_text,
        text_index_name=settings.text_index_name,
        limit=inner_limit,
    )
    fusion = {
        "$rankFusion": {
            "input": {
                "pipelines": {
                    "vector": vector_pipeline,
                    "text": text_pipeline,
                }
            },
            "combination": {
                "weights": {
                    "vector": settings.vector_weight,
                    "text": settings.text_weight,
                }
            },
            "scoreDetails": True,
        }
    }
    if rerank:
        # The fusion order only decides which candidates reach the reranker when
        # the two halves return more than rerank_candidates between them.
        return [
            fusion,
            {"$limit": settings.rerank_candidates},
            *_rerank_stages(query_text, settings=settings),
            {"$project": {"vector": 0}},
        ]
    return [
        fusion,
        {"$addFields": {"hybrid_score": {"$meta": "score"}}},
        {"$limit": top_k},
        {"$project": {"vector": 0}},
    ]


def _docs_to_results(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for doc in docs:
        result: dict[str, Any] = {
            "file_path": doc.get("file_path", ""),
            "content": doc.get("content", ""),
            "score": float(doc.get("hybrid_score") or 0.0),
        }
        for field in ("page", "start_line", "end_line"):
            if doc.get(field) is not None:
                result[field] = doc[field]
        results.append(result)
    return results


async def _pipeline_search(
    pipeline: list[dict[str, Any]],
    *,
    collection: AsyncIOMotorCollection,
    pipeline_type: RetrievalPipeline,
    reranked: bool = False,
) -> SearchResult:
    docs = await _run_search_pipeline(collection, pipeline)
    return SearchResult(
        references=_docs_to_results(docs),
        pipeline=pipeline_type,
        reranked=reranked,
    )


async def _keyword_search(
    query_text: str,
    *,
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
    rerank: bool = False,
) -> SearchResult:
    pipeline = build_text_search_pipeline(query_text, settings=settings, rerank=rerank)
    return await _pipeline_search(
        pipeline,
        collection=collection,
        pipeline_type=RetrievalPipeline.KEYWORD,
        reranked=rerank,
    )


async def _vector_search(
    query_text: str,
    *,
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
    rerank: bool = False,
) -> SearchResult:
    pipeline = build_vector_search_pipeline(query_text, settings=settings, rerank=rerank)
    return await _pipeline_search(
        pipeline,
        collection=collection,
        pipeline_type=RetrievalPipeline.VECTOR,
        reranked=rerank,
    )


async def _rank_fusion_search(
    query_text: str,
    *,
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
    rerank: bool = False,
) -> SearchResult:
    pipeline = build_rank_fusion_pipeline(query_text, settings=settings, rerank=rerank)
    return await _pipeline_search(
        pipeline,
        collection=collection,
        pipeline_type=RetrievalPipeline.RANK_FUSION,
        reranked=rerank,
    )


async def search_with_modes(
    query_text: str,
    *,
    modes: SearchModes,
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
) -> SearchResult:
    modes.validate_retrieval()
    # The rerank follows whichever retrieval is on, so the switches can be compared
    # one at a time: it can only reorder what that retrieval found.
    rerank = modes.rerank

    if modes.keyword and not modes.vector:
        return await _keyword_search(
            query_text, collection=collection, settings=settings, rerank=rerank
        )

    if modes.vector and not modes.keyword:
        return await _vector_search(
            query_text, collection=collection, settings=settings, rerank=rerank
        )

    return await _rank_fusion_search(
        query_text, collection=collection, settings=settings, rerank=rerank
    )


async def search(
    query_text: str,
    *,
    collection: AsyncIOMotorCollection,
    settings: HybridSearchSettings,
) -> list[dict[str, Any]]:
    result = await search_with_modes(
        query_text,
        modes=SearchModes(keyword=True, vector=True, llm=True),
        collection=collection,
        settings=settings,
    )
    return result.references


async def _run_search_pipeline(
    collection: AsyncIOMotorCollection,
    pipeline: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cursor = collection.aggregate(pipeline, allowDiskUse=True)
    return await cursor.to_list(length=None)
