from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

import hybrid_search.llm as llm_module
import hybrid_search.rewrite as rewrite_module
from hybrid_search.generate import Turn
from hybrid_search.settings import HybridSearchSettings

_HISTORY = [
    Turn(question="Where are we with Lisa's treatment?", answer="Lisa sees Dr. Feld next."),
    Turn(question="When is that visit?", answer="December 9."),
]


def _settings(**overrides: object) -> HybridSearchSettings:
    return HybridSearchSettings(
        mongodb_uri=SecretStr("mongodb://localhost"),
        anthropic_api_key=SecretStr("anthropic-key"),
        **overrides,
    )


def _patch_model(monkeypatch, reply: str) -> AsyncMock:
    mock_run = AsyncMock(return_value=reply)
    monkeypatch.setattr(llm_module, "run_prompt", mock_run)
    return mock_run


@pytest.mark.asyncio
async def test_rewrite_followup_returns_the_standalone_question(monkeypatch):
    mock_run = _patch_model(monkeypatch, "What will Lisa's visit with Dr. Feld cost?")

    search_text = await rewrite_module.rewrite_followup(
        "and what will it cost?", _HISTORY, settings=_settings()
    )

    assert search_text == "What will Lisa's visit with Dr. Feld cost?"
    assert mock_run.await_args.args[0] == (
        "Conversation so far:\n"
        "User: Where are we with Lisa's treatment?\nAssistant: Lisa sees Dr. Feld next.\n\n"
        "User: When is that visit?\nAssistant: December 9.\n\n"
        "Latest message: and what will it cost?\n\n"
        "Standalone question:"
    )
    # Its own system prompt: the RAG prompt would have the model answer.
    assert mock_run.await_args.kwargs["system_prompt"] == rewrite_module.REWRITE_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_rewrite_followup_makes_no_model_call_on_the_first_message(monkeypatch):
    mock_run = _patch_model(monkeypatch, "unused")

    search_text = await rewrite_module.rewrite_followup("first question", [], settings=_settings())

    assert search_text == "first question"
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewrite_followup_makes_no_model_call_when_history_is_off(monkeypatch):
    mock_run = _patch_model(monkeypatch, "unused")

    search_text = await rewrite_module.rewrite_followup(
        "and what will it cost?", _HISTORY, settings=_settings(llm_history_turns=0)
    )

    assert search_text == "and what will it cost?"
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewrite_followup_sends_only_the_most_recent_turns(monkeypatch):
    mock_run = _patch_model(monkeypatch, "What will the December 9 visit cost?")

    await rewrite_module.rewrite_followup(
        "and what will it cost?", _HISTORY, settings=_settings(llm_history_turns=1)
    )

    prompt = mock_run.await_args.args[0]
    assert "When is that visit?" in prompt
    assert "Where are we with Lisa's treatment?" not in prompt


@pytest.mark.asyncio
async def test_rewrite_followup_keeps_the_message_as_typed_when_the_model_returns_it(monkeypatch):
    # Same words, other case and spacing: the search runs on what was typed.
    _patch_model(monkeypatch, "what is the status of  pa-2026-0447?\n")

    search_text = await rewrite_module.rewrite_followup(
        "What is the status of PA-2026-0447?", _HISTORY, settings=_settings()
    )

    assert search_text == "What is the status of PA-2026-0447?"


@pytest.mark.asyncio
async def test_rewrite_followup_drops_wrapping_quotes_and_line_breaks(monkeypatch):
    _patch_model(monkeypatch, '  "What will Lisa\'s visit\nwith Dr. Feld cost?"  ')

    search_text = await rewrite_module.rewrite_followup(
        "and what will it cost?", _HISTORY, settings=_settings()
    )

    assert search_text == "What will Lisa's visit with Dr. Feld cost?"


@pytest.mark.asyncio
async def test_rewrite_followup_keeps_quotes_that_do_not_wrap_the_whole_reply(monkeypatch):
    _patch_model(monkeypatch, '"Tier 2" or "Tier 3"')

    search_text = await rewrite_module.rewrite_followup(
        "which tier is it?", _HISTORY, settings=_settings()
    )

    assert search_text == '"Tier 2" or "Tier 3"'


@pytest.mark.parametrize(
    "reply",
    ["", "   \n", "x" * (rewrite_module.MAX_SEARCH_TEXT_CHARS + 1)],
    ids=["empty", "blank", "too long to be a question"],
)
@pytest.mark.asyncio
async def test_rewrite_followup_falls_back_to_the_message_on_an_unusable_reply(monkeypatch, reply):
    _patch_model(monkeypatch, reply)

    search_text = await rewrite_module.rewrite_followup(
        "and what will it cost?", _HISTORY, settings=_settings()
    )

    assert search_text == "and what will it cost?"
