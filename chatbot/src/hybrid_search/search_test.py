from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from hybrid_search.search import (
    RetrievalPipeline,
    build_rank_fusion_pipeline,
    build_text_search_pipeline,
    build_vector_search_pipeline,
)
from hybrid_search.search_modes import SearchModes
from hybrid_search.settings import HybridSearchSettings

# The package re-exports the search function under the same name, so
# "import hybrid_search.search as ..." would bind the function, not the module.
search_module = importlib.import_module("hybrid_search.search")


def test_rank_fusion_pipeline_shape():
    settings = HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        top_k=20,
        vector_weight=0.6,
        text_weight=0.4,
    )
    pipeline = build_rank_fusion_pipeline("risk", settings=settings)
    fusion = pipeline[0]["$rankFusion"]
    assert fusion["combination"]["weights"] == {"vector": 0.6, "text": 0.4}
    assert fusion["input"]["pipelines"]["vector"][-1] == {"$limit": 40}
    assert fusion["input"]["pipelines"]["text"][-1] == {"$limit": 40}
    assert fusion["input"]["pipelines"]["vector"][0]["$vectorSearch"]["query"] == {"text": "risk"}
    assert "queryVector" not in str(fusion["input"]["pipelines"]["vector"])
    assert pipeline[1] == {"$addFields": {"hybrid_score": {"$meta": "score"}}}
    assert pipeline[2] == {"$limit": 20}
    assert pipeline[3] == {"$project": {"vector": 0}}


def test_text_search_pipeline_shape():
    settings = HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        top_k=5,
    )
    pipeline = build_text_search_pipeline("risk", settings=settings)
    assert pipeline[0]["$search"]["index"] == "text_idx"
    assert pipeline[1] == {"$limit": 5}
    assert pipeline[2] == {"$addFields": {"hybrid_score": {"$meta": "searchScore"}}}


def test_vector_search_pipeline_shape():
    settings = HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        top_k=5,
    )
    pipeline = build_vector_search_pipeline("risk", settings=settings)
    vector_stage = pipeline[0]["$vectorSearch"]
    assert vector_stage["index"] == "autoembed_idx"
    assert vector_stage["path"] == "content"
    assert vector_stage["query"] == {"text": "risk"}
    assert "queryVector" not in vector_stage
    assert pipeline[1] == {"$limit": 5}
    assert pipeline[2] == {"$addFields": {"hybrid_score": {"$meta": "vectorSearchScore"}}}
    assert pipeline[3] == {"$project": {"vector": 0}}


def _rerank_settings(**overrides: object) -> HybridSearchSettings:
    return HybridSearchSettings(mongodb_uri=SecretStr("mongodb://localhost"), **overrides)


_RERANK_TAIL = [
    {"$match": {"content": {"$type": "string"}}},
    {
        "$rerank": {
            "model": "rerank-2.5",
            "query": {"text": "risk"},
            "path": "content",
            "numDocsToRerank": 80,
        }
    },
    {"$addFields": {"hybrid_score": {"$meta": "score"}}},
    {"$limit": 20},
    {"$project": {"vector": 0}},
]


def test_rank_fusion_pipeline_reranks_every_candidate_then_cuts_to_top_k():
    pipeline = build_rank_fusion_pipeline("risk", settings=_rerank_settings(), rerank=True)

    fusion = pipeline[0]["$rankFusion"]
    # 40 from each half, as without a rerank: 80 candidates in all.
    assert fusion["input"]["pipelines"]["vector"][-1] == {"$limit": 40}
    assert fusion["input"]["pipelines"]["text"][-1] == {"$limit": 40}
    assert fusion["input"]["pipelines"]["vector"][0]["$vectorSearch"]["numCandidates"] == 400
    # $rerank cannot sit inside a fusion input pipeline, so it follows the fusion.
    assert pipeline[1] == {"$limit": 80}
    assert pipeline[2:] == _RERANK_TAIL


def test_rank_fusion_pipeline_widens_the_halves_for_more_rerank_candidates():
    pipeline = build_rank_fusion_pipeline(
        "risk", settings=_rerank_settings(rerank_candidates=201), rerank=True
    )

    fusion = pipeline[0]["$rankFusion"]
    assert fusion["input"]["pipelines"]["vector"][-1] == {"$limit": 101}
    assert fusion["input"]["pipelines"]["text"][-1] == {"$limit": 101}
    assert pipeline[1] == {"$limit": 201}


def test_rank_fusion_pipeline_is_unchanged_without_a_rerank():
    settings = _rerank_settings()
    assert build_rank_fusion_pipeline("risk", settings=settings) == build_rank_fusion_pipeline(
        "risk", settings=settings, rerank=False
    )
    assert "$rerank" not in str(build_rank_fusion_pipeline("risk", settings=settings))


def test_text_search_pipeline_reranks_the_candidates():
    pipeline = build_text_search_pipeline("risk", settings=_rerank_settings(), rerank=True)

    assert pipeline[0]["$search"]["index"] == "text_idx"
    assert pipeline[1] == {"$limit": 80}
    assert pipeline[2:] == _RERANK_TAIL


def test_vector_search_pipeline_reranks_the_candidates():
    pipeline = build_vector_search_pipeline("risk", settings=_rerank_settings(), rerank=True)

    vector_stage = pipeline[0]["$vectorSearch"]
    assert vector_stage["limit"] == 80
    assert vector_stage["numCandidates"] == 1600
    assert pipeline[1] == {"$limit": 80}
    assert pipeline[2:] == _RERANK_TAIL


def test_vector_search_pipeline_caps_num_candidates():
    pipeline = build_vector_search_pipeline(
        "risk", settings=_rerank_settings(rerank_candidates=1000), rerank=True
    )

    assert pipeline[0]["$vectorSearch"]["numCandidates"] == 10_000


def test_rerank_uses_the_configured_model():
    pipeline = build_text_search_pipeline(
        "risk", settings=_rerank_settings(rerank_model="rerank-3"), rerank=True
    )

    assert pipeline[3]["$rerank"]["model"] == "rerank-3"


@pytest.mark.parametrize(
    ("modes", "expected_pipeline"),
    [
        (SearchModes(rerank=True), RetrievalPipeline.RANK_FUSION),
        (SearchModes(vector=False, rerank=True), RetrievalPipeline.KEYWORD),
        (SearchModes(keyword=False, rerank=True), RetrievalPipeline.VECTOR),
    ],
    ids=["hybrid", "keyword only", "vector only"],
)
@pytest.mark.asyncio
async def test_search_with_modes_reranks_whichever_retrieval_is_on(modes, expected_pipeline):
    ran: list[list[dict]] = []

    async def fake_run(collection, pipeline):
        ran.append(pipeline)
        return [{"file_path": "a.md", "content": "c", "hybrid_score": 0.9}]

    with patch.object(search_module, "_run_search_pipeline", fake_run):
        result = await search_module.search_with_modes(
            "risk", modes=modes, collection=MagicMock(), settings=_rerank_settings()
        )

    assert result.pipeline == expected_pipeline
    assert result.reranked is True
    assert result.references[0]["score"] == 0.9
    assert any("$rerank" in stage for stage in ran[0])


@pytest.mark.asyncio
async def test_search_with_modes_does_not_rerank_unless_the_mode_is_on():
    ran: list[list[dict]] = []

    async def fake_run(collection, pipeline):
        ran.append(pipeline)
        return []

    with patch.object(search_module, "_run_search_pipeline", fake_run):
        result = await search_module.search_with_modes(
            "risk", modes=SearchModes(), collection=MagicMock(), settings=_rerank_settings()
        )

    assert result.reranked is False
    assert not any("$rerank" in stage for stage in ran[0])
