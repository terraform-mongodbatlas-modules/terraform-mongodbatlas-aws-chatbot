from __future__ import annotations

import pytest

from hybrid_search.search_modes import SearchModes
from hybrid_search.ui.search_settings import (
    build_chat_settings,
    confirmation_message,
    default_modes,
    modes_from_settings,
)


def test_modes_from_settings_round_trip():
    modes = SearchModes(keyword=True, vector=False, llm=False)
    assert modes_from_settings({"keyword": True, "vector": False, "llm": False}) == modes


def test_modes_from_settings_defaults():
    assert modes_from_settings({}) == SearchModes()


def test_modes_from_settings_rejects_both_retrieval_off():
    with pytest.raises(ValueError, match="keyword or vector"):
        modes_from_settings({"keyword": False, "vector": False, "llm": True})


def test_modes_from_settings_reads_the_rewrite_switch():
    settings = {"keyword": True, "vector": True, "llm": True, "rewrite": False}
    assert modes_from_settings(settings) == SearchModes(rewrite=False)


def test_default_modes_take_the_rewrite_default_from_the_deployment():
    assert default_modes(rewrite_followups=True) == SearchModes()
    assert default_modes(rewrite_followups=False) == SearchModes(rewrite=False)


def test_confirmation_message_names_follow_up_rewriting_only_when_it_runs():
    assert confirmation_message(SearchModes()) == (
        "Search modes: keyword, semantic, LLM, follow-up rewriting."
    )
    assert (
        confirmation_message(SearchModes(rewrite=False)) == "Search modes: keyword, semantic, LLM."
    )
    # Switch on, LLM off: no model call is made, so it is not listed.
    assert confirmation_message(SearchModes(llm=False)) == "Search modes: keyword, semantic."


def _switch_ids(chat_settings) -> list[str]:
    return [widget.id for widget in chat_settings.inputs]


def test_chat_settings_show_the_rerank_switch_only_where_it_is_available():
    assert _switch_ids(build_chat_settings(SearchModes())) == [
        "keyword",
        "vector",
        "llm",
        "rewrite",
    ]

    with_rerank = build_chat_settings(SearchModes(rerank=True), rerank_available=True)
    assert _switch_ids(with_rerank) == ["keyword", "vector", "llm", "rewrite", "rerank"]
    assert with_rerank.inputs[-1].initial is True


def test_modes_from_settings_reads_the_rerank_switch():
    assert modes_from_settings({"rerank": True}) == SearchModes(rerank=True)
    # No switch was sent: the deployment has no rerank.
    assert modes_from_settings({}).rerank is False


def test_default_modes_start_with_the_rerank_on_where_the_deployment_enabled_it():
    assert default_modes(rewrite_followups=True, rerank=True) == SearchModes(rerank=True)
    assert default_modes(rewrite_followups=True) == SearchModes(rerank=False)


def test_confirmation_message_names_the_rerank():
    assert confirmation_message(SearchModes(rerank=True)) == (
        "Search modes: keyword, semantic, LLM, follow-up rewriting, rerank."
    )


def test_chat_settings_call_the_vector_switch_semantic_search():
    labels = {widget.id: widget.label for widget in build_chat_settings(SearchModes()).inputs}
    assert labels["vector"] == "Semantic search"
    assert labels["keyword"] == "Keyword search"
