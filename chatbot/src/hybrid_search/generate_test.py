from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

import hybrid_search.generate as generate_module
import hybrid_search.llm as llm_module
from hybrid_search.settings import HybridSearchSettings


def test_unique_source_files_basenames_dedupe_skip_unknown():
    refs = [
        {"file_path": "/data/NIST.AI.100-1.pdf"},
        {"file_path": "uploads/NIST.AI.100-1.pdf"},
        {"file_path": "unknown_source"},
        {"file_path": ""},
        {"file_path": "owasp.md"},
    ]
    assert generate_module.unique_source_files(refs) == ["NIST.AI.100-1.pdf", "owasp.md"]


@pytest.mark.asyncio
async def test_generate_answer_retrieval_only():
    settings = HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        enable_llm=False,
    )
    result = await generate_module.generate_answer(
        "question",
        [{"file_path": "a.pdf", "content": "ctx"}],
        settings=settings,
    )
    assert "Retrieval-only" in result.answer
    assert generate_module.unique_source_files([{"file_path": "a.pdf"}]) == ["a.pdf"]


@pytest.mark.asyncio
async def test_generate_answer_calls_llm(monkeypatch):
    settings = HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        anthropic_api_key=SecretStr("anthropic-key"),
    )
    mock_run = AsyncMock(return_value="answer text")
    monkeypatch.setattr(llm_module, "run_rag_prompt", mock_run)
    result = await generate_module.generate_answer(
        "q", [{"file_path": "b.md", "content": "c"}], settings=settings
    )
    assert result.answer == "answer text"


@pytest.mark.asyncio
async def test_generate_answer_limits_context_to_llm_max_snippets(monkeypatch):
    settings = HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        anthropic_api_key=SecretStr("anthropic-key"),
        llm_max_snippets=1,
    )
    mock_run = AsyncMock(return_value="answer text")
    monkeypatch.setattr(llm_module, "run_rag_prompt", mock_run)
    references = [{"file_path": "a.pdf", "content": f"snippet {index}"} for index in range(3)]

    await generate_module.generate_answer("q", references, settings=settings)

    prompt = mock_run.await_args.args[0]
    assert "snippet 0" in prompt
    assert "snippet 1" not in prompt
    assert "snippet 2" not in prompt


def _llm_settings(**overrides: object) -> HybridSearchSettings:
    return HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        anthropic_api_key=SecretStr("anthropic-key"),
        **overrides,
    )


_HISTORY = [
    generate_module.Turn(question="first question", answer="first answer"),
    generate_module.Turn(question="second question", answer="second answer"),
]
_ONE_REFERENCE = [{"file_path": "b.md", "content": "c"}]


def test_recent_turns_keeps_the_last_turns_and_none_for_zero():
    assert generate_module.recent_turns(_HISTORY, 5) == _HISTORY
    assert generate_module.recent_turns(_HISTORY, 1) == _HISTORY[1:]
    assert generate_module.recent_turns(_HISTORY, 0) == []


@pytest.mark.asyncio
async def test_generate_answer_prompt_is_unchanged_without_history(monkeypatch):
    mock_run = AsyncMock(return_value="answer text")
    monkeypatch.setattr(llm_module, "run_rag_prompt", mock_run)

    await generate_module.generate_answer("q", _ONE_REFERENCE, settings=_llm_settings())

    assert mock_run.await_args.args[0] == (
        "Answer the question using only the context snippets. "
        "If the context is insufficient, say so briefly.\n\n"
        "Question: q\n\nContext:\nc"
    )


@pytest.mark.asyncio
async def test_generate_answer_puts_earlier_turns_before_the_question(monkeypatch):
    mock_run = AsyncMock(return_value="answer text")
    monkeypatch.setattr(llm_module, "run_rag_prompt", mock_run)

    await generate_module.generate_answer(
        "and the next one?", _ONE_REFERENCE, settings=_llm_settings(), history=_HISTORY
    )

    prompt = mock_run.await_args.args[0]
    assert prompt.endswith(
        "Conversation so far:\n"
        "User: first question\nAssistant: first answer\n\n"
        "User: second question\nAssistant: second answer\n\n"
        "Question: and the next one?\n\nContext:\nc"
    )
    assert "earlier answers in this conversation" in prompt


@pytest.mark.asyncio
async def test_generate_answer_keeps_only_the_most_recent_turns(monkeypatch):
    mock_run = AsyncMock(return_value="answer text")
    monkeypatch.setattr(llm_module, "run_rag_prompt", mock_run)

    await generate_module.generate_answer(
        "q", _ONE_REFERENCE, settings=_llm_settings(llm_history_turns=1), history=_HISTORY
    )

    prompt = mock_run.await_args.args[0]
    assert "second question" in prompt
    assert "first question" not in prompt


@pytest.mark.asyncio
async def test_generate_answer_ignores_history_when_turns_is_zero(monkeypatch):
    mock_run = AsyncMock(return_value="answer text")
    monkeypatch.setattr(llm_module, "run_rag_prompt", mock_run)

    await generate_module.generate_answer(
        "q", _ONE_REFERENCE, settings=_llm_settings(llm_history_turns=0), history=_HISTORY
    )

    prompt = mock_run.await_args.args[0]
    assert "Conversation so far" not in prompt
    assert "second question" not in prompt
