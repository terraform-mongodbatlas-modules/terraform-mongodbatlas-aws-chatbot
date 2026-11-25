from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchModes:
    keyword: bool = True
    vector: bool = True
    llm: bool = True
    # Restate a follow-up as a standalone question before the search runs.
    rewrite: bool = True
    # Reorder the retrieved candidates with $rerank. Off unless the deployment
    # enables it (settings.rerank_enabled): the stage is not available everywhere.
    rerank: bool = False

    @property
    def rewrites_followups(self) -> bool:
        # The rewrite is a model call, so "LLM answer" off turns it off too: with the
        # LLM off the chat makes no model call and searches for the message as typed.
        return self.llm and self.rewrite

    def validate_retrieval(self) -> None:
        if self.keyword or self.vector:
            return
        msg = "At least one of keyword or vector must be enabled"
        raise ValueError(msg)


DEFAULT = SearchModes()
