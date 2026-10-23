from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from hybrid_search.search import RetrievalPipeline, SearchResult
from hybrid_search.search_modes import SearchModes
from hybrid_search.settings import HybridSearchSettings
from hybrid_search.ui import query_steps
from hybrid_search.ui.query_logic import QueryResult

_REFERENCES = [{"file_path": "docs/a.pdf", "content": "ctx", "score": 0.9}]
_SEARCH_RESULT = SearchResult(
    references=_REFERENCES,
    pipeline=RetrievalPipeline.RANK_FUSION,
)
_SETTINGS = HybridSearchSettings(mongodb_uri=SecretStr("mongodb://localhost"))
_MODULE = query_steps.__name__


class _FakeStepCtx:
    def __init__(self, **kwargs):
        self.name = kwargs.get("name")
        self.type = kwargs.get("type")
        self.output = None
        self.update = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def _chainlit_stack(stack: ExitStack, steps: list[_FakeStepCtx] | None = None):
    class RecordingStepCtx(_FakeStepCtx):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            if steps is not None:
                steps.append(self)

    stack.enter_context(patch.object(query_steps.cl, "Step", RecordingStepCtx))


@pytest.mark.asyncio
async def test_run_query_with_steps_calls_retrieve_then_answer():
    retrieve = AsyncMock(return_value=_SEARCH_RESULT)
    answer = AsyncMock(
        return_value=QueryResult(
            references=_REFERENCES,
            answer="generated",
            modes=SearchModes(),
            search_result=_SEARCH_RESULT,
        )
    )
    with ExitStack() as stack:
        _chainlit_stack(stack)
        stack.enter_context(patch(f"{_MODULE}.retrieve", retrieve))
        stack.enter_context(patch(f"{_MODULE}.answer_or_format", answer))
        result = await query_steps.run_query_with_steps(
            "risk",
            settings=_SETTINGS,
            collection=MagicMock(),
            modes=SearchModes(),
        )

    retrieve.assert_awaited_once()
    answer.assert_awaited_once()
    assert answer.await_args.args[1] == _SEARCH_RESULT
    assert result.answer == "generated"


@pytest.mark.asyncio
async def test_run_query_with_steps_retrieval_only_formats_in_answer_step():
    retrieve = AsyncMock(return_value=_SEARCH_RESULT)
    answer = AsyncMock(
        return_value=QueryResult(
            references=_REFERENCES,
            answer=None,
            modes=SearchModes(keyword=True, vector=True, llm=False),
            search_result=_SEARCH_RESULT,
        )
    )
    steps: list[_FakeStepCtx] = []
    with ExitStack() as stack:
        _chainlit_stack(stack, steps)
        stack.enter_context(patch(f"{_MODULE}.retrieve", retrieve))
        stack.enter_context(patch(f"{_MODULE}.answer_or_format", answer))
        await query_steps.run_query_with_steps(
            "risk",
            settings=_SETTINGS,
            collection=MagicMock(),
            modes=SearchModes(keyword=True, vector=True, llm=False),
        )

    answer.assert_awaited_once()
    answer_step = next(step for step in steps if step.name == "Answer")
    assert answer_step.output is not None
    assert "a.pdf" in answer_step.output


@pytest.mark.asyncio
async def test_run_query_with_steps_emits_one_collapsible_step_per_hit():
    refs = [
        {
            "file_path": "docs/a.md",
            "content": "```hcl\nx\n```",
            "score": 2.0,
            "start_line": 1,
            "end_line": 3,
        },
        {"file_path": "docs/b.md", "content": "plain chunk", "score": 1.0},
    ]
    search_result = SearchResult(references=refs, pipeline=RetrievalPipeline.RANK_FUSION)
    retrieve = AsyncMock(return_value=search_result)
    answer = AsyncMock(
        return_value=QueryResult(
            references=refs,
            answer=None,
            modes=SearchModes(keyword=True, vector=True, llm=False),
            search_result=search_result,
        )
    )
    steps: list[_FakeStepCtx] = []
    with ExitStack() as stack:
        _chainlit_stack(stack, steps)
        stack.enter_context(patch(f"{_MODULE}.retrieve", retrieve))
        stack.enter_context(patch(f"{_MODULE}.answer_or_format", answer))
        await query_steps.run_query_with_steps(
            "risk",
            settings=_SETTINGS,
            collection=MagicMock(),
            modes=SearchModes(keyword=True, vector=True, llm=False),
        )

    names = [step.name for step in steps]
    assert "1 · a.md · lines 1-3 · 2.000" in names
    assert "2 · b.md · 1.000" in names

    hit = next(step for step in steps if step.name == "1 · a.md · lines 1-3 · 2.000")
    assert hit.type == "tool"
    assert "````\n```hcl\nx\n```\n````" in hit.output

    # The chunk bodies live in the hit steps now, so the answer step must not repeat them.
    answer_step = next(step for step in steps if step.name == "Answer")
    assert "```hcl" not in answer_step.output
    assert "a.md" in answer_step.output


@pytest.mark.asyncio
async def test_run_query_with_steps_puts_retrieval_summary_in_the_step_header():
    retrieve = AsyncMock(return_value=_SEARCH_RESULT)
    answer = AsyncMock(
        return_value=QueryResult(
            references=_REFERENCES,
            answer=None,
            modes=SearchModes(keyword=True, vector=True, llm=False),
            search_result=_SEARCH_RESULT,
        )
    )
    steps: list[_FakeStepCtx] = []
    with ExitStack() as stack:
        _chainlit_stack(stack, steps)
        stack.enter_context(patch(f"{_MODULE}.retrieve", retrieve))
        stack.enter_context(patch(f"{_MODULE}.answer_or_format", answer))
        await query_steps.run_query_with_steps(
            "risk",
            settings=_SETTINGS,
            collection=MagicMock(),
            modes=SearchModes(keyword=True, vector=True, llm=False),
        )

    # The summary is the retrieval step's header, so it renders above the hit steps.
    retrieval_step = next(step for step in steps if step.name.startswith("Keyword + vector"))
    assert retrieval_step.type == "tool"
    assert retrieval_step.name == "Keyword + vector retrieval ($rankFusion) · 1 hit"


@pytest.mark.asyncio
async def test_retrieval_status_counts_hits():
    one = query_steps._retrieval_status(
        SearchResult(references=_REFERENCES, pipeline=RetrievalPipeline.RANK_FUSION),
        SearchModes(keyword=True, vector=True),
    )
    two = query_steps._retrieval_status(
        SearchResult(
            references=[*_REFERENCES, *_REFERENCES], pipeline=RetrievalPipeline.RANK_FUSION
        ),
        SearchModes(keyword=True, vector=True),
    )
    assert one == "Keyword + vector retrieval ($rankFusion) · 1 hit"
    assert two == "Keyword + vector retrieval ($rankFusion) · 2 hits"


@pytest.mark.asyncio
async def test_retrieval_status_keyword_only():
    status = query_steps._retrieval_status(
        SearchResult(references=[], pipeline=RetrievalPipeline.KEYWORD),
        SearchModes(keyword=True, vector=False),
    )
    assert status == "Keyword search (no query embedding)"
