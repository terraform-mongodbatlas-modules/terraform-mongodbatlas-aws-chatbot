from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import chainlit as cl
from motor.motor_asyncio import AsyncIOMotorCollection

from hybrid_search.generate import Turn
from hybrid_search.rewrite import rewrite_followup
from hybrid_search.search import SearchResult
from hybrid_search.search_modes import SearchModes
from hybrid_search.settings import HybridSearchSettings
from hybrid_search.ui.query_logic import QueryResult, answer_or_format, retrieve
from hybrid_search.ui.result_format import (
    format_hit_body,
    format_location,
    hit_label,
    retrieval_header,
)

logger = logging.getLogger(__name__)


def _retrieval_status(search_result: SearchResult, modes: SearchModes) -> str:
    # With a rerank the hit scores below are rerank scores, so the header says so.
    reranked = " · reranked ($rerank)" if search_result.reranked else ""
    if not modes.vector:
        return f"Keyword search (no query embedding){reranked}"
    header = retrieval_header(search_result.pipeline)
    count = len(search_result.references)
    noun = "hit" if count == 1 else "hits"
    return f"{header}{reranked} · {count} {noun}"


def _source_lines(references: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for ref in references:
        filename = Path(ref.get("file_path", "")).name or "unknown"
        location = format_location(ref)
        label = f"{filename} · {location}" if location else filename
        if label in seen:
            continue
        seen.add(label)
        lines.append(label)
    return lines


def _answer_output(result: QueryResult) -> str:
    lines = _source_lines(result.references)
    if lines:
        footer = "### Sources\n" + "\n".join(f"- {line}" for line in lines)
    else:
        footer = "### Sources\nNo sources retrieved"
    if result.answer:
        return f"{result.answer}\n\n{footer}"
    return footer


async def _emit_hit_steps(references: list[dict[str, Any]]) -> None:
    # One collapsed step per hit, so a viewer opens only the chunk they care about.
    # type="tool" is what keeps the step visible: the app runs config ui.cot =
    # "tool_call", and Chainlit only renders the header of tool steps in that mode.
    for index, ref in enumerate(references, start=1):
        async with cl.Step(name=hit_label(index, ref), type="tool") as hit_step:
            hit_step.output = format_hit_body(ref)
            await hit_step.update()


async def _search_text(
    query: str,
    *,
    settings: HybridSearchSettings,
    modes: SearchModes,
    history: Sequence[Turn],
) -> str:
    # Only a follow-up is rewritten. The first message of a chat has nothing to
    # refer back to, so it is searched as typed and costs no extra model call.
    if not (modes.rewrites_followups and settings.enable_llm and history):
        return query
    # The outcome goes in the step header, so a viewer sees what was searched for
    # without opening the step.
    async with cl.Step(name="Rewriting follow-up", type="tool") as step:
        try:
            search_text = await rewrite_followup(query, history, settings=settings)
        except Exception as exc:
            # The search can still run on the message as typed, so a failed
            # rewrite is reported in the step and does not fail the question.
            logger.exception("Follow-up rewrite failed")
            search_text = query
            step.name = "Follow-up rewrite failed · searching as typed"
            step.output = f"The search ran on the message as typed.\n\nRewrite error: {exc}"
        else:
            if search_text == query:
                step.name = "Follow-up stands on its own · searching as typed"
            else:
                step.name = f"Searching for: {search_text}"
            step.output = f"**Typed:** {query}\n\n**Searched for:** {search_text}"
        await step.update()
    return search_text


async def run_query_with_steps(
    query: str,
    *,
    settings: HybridSearchSettings,
    collection: AsyncIOMotorCollection,
    modes: SearchModes,
    history: Sequence[Turn] = (),
) -> QueryResult:
    async with cl.Step(name="Query", type="run"):
        search_text = await _search_text(query, settings=settings, modes=modes, history=history)
        async with cl.Step(name="Retrieving", type="tool") as retrieve_step:
            search_result = await retrieve(
                search_text,
                modes=modes,
                settings=settings,
                collection=collection,
            )
            # A step renders its nested steps before its own output, so the summary
            # would sit below the hit steps if it were the output. Renaming the header
            # puts it at the top of the section, where the summary belongs.
            retrieve_step.name = _retrieval_status(search_result, modes)
            await retrieve_step.update()
            await _emit_hit_steps(search_result.references)

        answer_type = "llm" if modes.llm and settings.enable_llm else "tool"
        async with cl.Step(name="Answer", type=answer_type) as answer_step:
            # The answer gets the question as typed plus the conversation; only the
            # search uses the rewritten text.
            result = await answer_or_format(
                query,
                search_result,
                modes=modes,
                settings=settings,
                history=history,
            )
            answer_step.output = _answer_output(result)
            await answer_step.update()
            return result
