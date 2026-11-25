from __future__ import annotations

import pytest

from hybrid_search.search_modes import DEFAULT, SearchModes


def test_search_modes_defaults():
    assert DEFAULT == SearchModes()
    assert DEFAULT.keyword and DEFAULT.vector and DEFAULT.llm


def test_search_modes_rejects_all_retrieval_off():
    with pytest.raises(ValueError, match="keyword or vector"):
        SearchModes(keyword=False, vector=False).validate_retrieval()


def test_search_modes_rewrite_follow_ups_by_default():
    assert DEFAULT.rewrite
    assert DEFAULT.rewrites_followups


def test_search_modes_no_follow_up_rewrite_without_the_llm():
    # The rewrite is a model call, so turning the LLM off turns it off too.
    assert not SearchModes(llm=False, rewrite=True).rewrites_followups
    assert not SearchModes(llm=True, rewrite=False).rewrites_followups


def test_search_modes_do_not_rerank_by_default():
    # $rerank is not available on every cluster, so a deployment has to turn it on.
    assert not DEFAULT.rerank
