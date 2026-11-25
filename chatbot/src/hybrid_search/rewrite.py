from __future__ import annotations

from collections.abc import Sequence

from hybrid_search import llm as llm_module
from hybrid_search.generate import Turn, format_conversation, recent_turns
from hybrid_search.settings import HybridSearchSettings

# The search only sees the text it is given. A follow-up such as "and what will it
# cost?" names nothing to search for, so the model first restates it as a question
# that stands on its own. This call gets its own system prompt: the RAG prompt tells
# the model to answer from context snippets, and here it must not answer at all.
REWRITE_SYSTEM_PROMPT = (
    "You prepare questions for a document search engine. You are given a conversation "
    "and the user's latest message. Restate the latest message as one question that "
    "can be understood without the conversation: replace pronouns and references such "
    "as 'it', 'that one' or 'her' with the names, identifiers and dates they refer "
    "to. Keep the user's own wording, and every name, number and identifier they "
    "wrote, exactly. If the latest message can already be understood on its own, or "
    "starts a new topic, return it word for word: add nothing from the conversation "
    "to a message that does not need it. Never answer the question. Reply with the "
    "question only, on one line, without quotes or commentary."
)
# A longer reply is the model answering or explaining instead of rewriting.
MAX_SEARCH_TEXT_CHARS = 400
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"))


async def rewrite_followup(
    query: str, history: Sequence[Turn], *, settings: HybridSearchSettings
) -> str:
    """Return the text to search for: the follow-up restated to stand on its own.

    The message comes back exactly as typed when there is no earlier turn to resolve
    it against (no model call is made), when the model returns it unchanged, and when
    the model's reply is not usable as a search.
    """
    turns = recent_turns(history, settings.llm_history_turns)
    if not turns:
        return query
    reply = await llm_module.run_prompt(
        _build_prompt(query, turns), settings=settings, system_prompt=REWRITE_SYSTEM_PROMPT
    )
    search_text = _usable_search_text(reply)
    if search_text is None or _same_text(search_text, query):
        return query
    return search_text


def _build_prompt(query: str, turns: Sequence[Turn]) -> str:
    return (
        f"Conversation so far:\n{format_conversation(turns)}\n\n"
        f"Latest message: {query}\n\n"
        "Standalone question:"
    )


def _usable_search_text(reply: str) -> str | None:
    text = " ".join(reply.split())
    for opening, closing in _QUOTE_PAIRS:
        inner = text[1:-1]
        # Only quotes wrapped around the whole reply go: a question that quotes a
        # phrase at its start and another at its end keeps both.
        if (
            len(text) >= 2
            and text.startswith(opening)
            and text.endswith(closing)
            and opening not in inner
            and closing not in inner
        ):
            text = inner.strip()
            break
    if not text or len(text) > MAX_SEARCH_TEXT_CHARS:
        return None
    return text


def _same_text(left: str, right: str) -> bool:
    return " ".join(left.split()).casefold() == " ".join(right.split()).casefold()
