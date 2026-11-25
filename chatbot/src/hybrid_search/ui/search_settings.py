from __future__ import annotations

from dataclasses import replace

import chainlit as cl
from chainlit.input_widget import Switch

from hybrid_search.search_modes import DEFAULT, SearchModes

SEARCH_MODES_KEY = "search_modes"
_KEYWORD = "keyword"
_VECTOR = "vector"
_LLM = "llm"
_REWRITE = "rewrite"
_RERANK = "rerank"


def build_chat_settings(modes: SearchModes, *, rerank_available: bool = False) -> cl.ChatSettings:
    switches = [
        Switch(id=_KEYWORD, label="Keyword search", initial=modes.keyword),
        Switch(id=_VECTOR, label="Vector search", initial=modes.vector),
        Switch(id=_LLM, label="LLM answer", initial=modes.llm),
        Switch(id=_REWRITE, label="Rewrite follow-ups", initial=modes.rewrite),
    ]
    if rerank_available:
        # Only where the deployment enabled it: $rerank is not available on every
        # cluster, and a switch that fails every question is worse than none.
        switches.append(Switch(id=_RERANK, label="Rerank results", initial=modes.rerank))
    return cl.ChatSettings(switches)


def modes_from_settings(settings: dict) -> SearchModes:
    modes = SearchModes(
        keyword=bool(settings.get(_KEYWORD, True)),
        vector=bool(settings.get(_VECTOR, True)),
        llm=bool(settings.get(_LLM, True)),
        rewrite=bool(settings.get(_REWRITE, True)),
        # Absent when the deployment has no rerank, so the default is off.
        rerank=bool(settings.get(_RERANK, False)),
    )
    modes.validate_retrieval()
    return modes


def confirmation_message(modes: SearchModes) -> str:
    active = [
        name
        for enabled, name in (
            (modes.keyword, "keyword"),
            (modes.vector, "vector"),
            (modes.llm, "LLM"),
            (modes.rewrites_followups, "follow-up rewriting"),
            (modes.rerank, "rerank"),
        )
        if enabled
    ]
    return f"Search modes: {', '.join(active)}."


def default_modes(*, rewrite_followups: bool, rerank: bool = False) -> SearchModes:
    # The switches start from the defaults, except the two a deployment sets.
    return replace(DEFAULT, rewrite=rewrite_followups, rerank=rerank)


async def send_default_settings(
    modes: SearchModes = DEFAULT, *, rerank_available: bool = False
) -> None:
    cl.user_session.set(SEARCH_MODES_KEY, modes)
    await build_chat_settings(modes, rerank_available=rerank_available).send()
