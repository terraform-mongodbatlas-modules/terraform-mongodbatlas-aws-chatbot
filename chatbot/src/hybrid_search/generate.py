from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hybrid_search import llm as llm_module
from hybrid_search.settings import HybridSearchSettings


@dataclass(frozen=True)
class GenerateResult:
    answer: str


@dataclass(frozen=True)
class Turn:
    """One earlier exchange of a chat session: the question as typed and the answer given."""

    question: str
    answer: str


def recent_turns(history: Sequence[Turn], max_turns: int) -> list[Turn]:
    # history[-0:] is the whole list, so zero turns needs its own branch.
    return list(history[-max_turns:]) if max_turns > 0 else []


def format_conversation(turns: Sequence[Turn]) -> str:
    return "\n\n".join(f"User: {turn.question}\nAssistant: {turn.answer}" for turn in turns)


def unique_source_files(references: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for ref in references:
        raw = ref.get("file_path", "")
        if raw in {"", "unknown_source"}:
            continue
        name = Path(raw).name
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


async def generate_answer(
    query: str,
    references: list[dict[str, Any]],
    *,
    settings: HybridSearchSettings,
    history: Sequence[Turn] = (),
) -> GenerateResult:
    if settings.enable_llm:
        context = _build_context(references, max_snippets=settings.llm_max_snippets)
        turns = recent_turns(history, settings.llm_history_turns)
        prompt = _build_prompt(query, context, history=turns)
        answer = await llm_module.run_rag_prompt(prompt, settings=settings)
        return GenerateResult(answer=answer)
    return GenerateResult(answer="Retrieval-only mode (ENABLE_LLM=false). See sources below.")


def _build_prompt(query: str, context: str, *, history: Sequence[Turn]) -> str:
    # The earlier turns travel as text in the prompt, not as model messages, so
    # every provider gets the same thing and the system prompt is sent as before.
    # Only the question and the answer of each turn are kept; the snippets
    # retrieved for earlier questions are not repeated.
    if not history:
        return (
            "Answer the question using only the context snippets. "
            "If the context is insufficient, say so briefly.\n\n"
            f"Question: {query}\n\nContext:\n{context}"
        )
    return (
        "Answer the question using only the context snippets and the earlier answers "
        "in this conversation. The conversation shows what the question refers to. "
        "If the snippets and the earlier answers are insufficient, say so briefly.\n\n"
        f"Conversation so far:\n{format_conversation(history)}\n\n"
        f"Question: {query}\n\nContext:\n{context}"
    )


def _build_context(references: list[dict[str, Any]], *, max_snippets: int) -> str:
    parts: list[str] = []
    for ref in references[:max_snippets]:
        content = ref.get("content", "").strip()
        if content:
            parts.append(content)
    return "\n---\n".join(parts)
