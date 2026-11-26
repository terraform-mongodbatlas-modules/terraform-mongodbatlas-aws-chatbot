from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LlmProvider = Literal["anthropic", "bedrock", "openai", "gemini", "grove"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Atlas Automated Embedding truncates text past the model context window silently, with
# no error at index time. voyage-4-lite and the other supported models share this window.
# https://www.mongodb.com/docs/vector-search/crud-embeddings/automated-embedding/models
AUTOEMBED_CONTEXT_TOKENS = 32_000
# Chunk-size envelope from the Atlas Search Playground chunking UI.
# https://www.mongodb.com/docs/vector-search/query/vector-search-playground/
MIN_CHUNK_MAX_TOKENS = 40
MAX_CHUNK_MAX_TOKENS = 1500

# The app's answer shape: grounded in the retrieved context, with short bullet
# points first and a paragraph of details after. Callers can override it through
# the RAG_SYSTEM_PROMPT env var.
DEFAULT_RAG_SYSTEM_PROMPT = (
    "You are a documentation-grounded assistant. Answer ONLY using the context "
    "snippets provided in the user message and never rely on outside knowledge. "
    "If the context is insufficient to answer the question, do not guess: reply "
    "exactly with \"Hmm, I don't know that one yet! Try uploading your own "
    'documents so I can help you better." When the context is sufficient, '
    "structure your reply as (1) a few short bullet points giving the direct "
    "answer, followed by (2) a brief paragraph with the supporting details and "
    "any caveats. Stay concise, reference the relevant sources by name where "
    "possible, and call out uncertainty explicitly."
)


class HybridSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    mongodb_uri: SecretStr
    # Atlas serves TLS; the plaintext Atlas Local container needs this off.
    mongodb_tls: bool = True
    mongodb_database: str = "hybrid_search"
    autoembed_model: str = "voyage-4-lite"
    # 512 tokens matches the Voyage auto-chunking default.
    # https://www.mongodb.com/docs/api/doc/atlas-embedding-and-reranking-api/voyage-context-4/operation/operation-createcontextualizedembedding
    chunk_max_tokens: int = 512
    top_k: int = 20
    vector_index_name: str = "autoembed_idx"
    text_index_name: str = "text_idx"
    chunks_collection: str = "chunks"
    vector_weight: float = 0.6
    text_weight: float = 0.4
    enable_llm: bool = True
    rag_system_prompt: str = DEFAULT_RAG_SYSTEM_PROMPT
    # Snippets the answer context keeps from the retrieved references (the
    # search pipeline orders hits by relevance first), so the prompt stays
    # bounded while top_k controls how much is retrieved.
    llm_max_snippets: int = Field(default=5, ge=1)
    # Earlier question-and-answer turns of a chat session sent to the model with
    # each new question, so a follow-up can refer back. 0 sends every question
    # on its own, and leaves nothing for rewrite_followups to work from.
    llm_history_turns: int = Field(default=10, ge=0)
    # The search only sees the text it is given, and a follow-up such as "and what
    # will it cost?" names nothing to search for. When true, the model first
    # restates a follow-up as a question that stands on its own, and the search
    # runs on that. One extra model call per follow-up; the first message of a
    # chat is never rewritten. This is the default of the chat's "Rewrite
    # follow-ups" switch, which a user can flip per session.
    rewrite_followups: bool = True
    # Reorder the retrieved candidates with Atlas native reranking ($rerank) before
    # the answer: a cross-encoder reads the question against each candidate, which
    # recovers an exact match that rank fusion buried and a paraphrase that keyword
    # search missed. Needs MongoDB 9.0 or later and Native Reranking enabled in the
    # Atlas project, so it is off unless a deployment turns it on. When true, the
    # chat shows a "Rerank results" switch, on at the start of each chat.
    rerank_enabled: bool = False
    rerank_model: str = "rerank-2.5"
    # Candidates the retrieval hands to the reranker. $rerank accepts at most 1000.
    rerank_candidates: int = Field(default=80, ge=1, le=1000)
    # The start screen shows "Upload documents" and "Delete documents" ahead of the
    # corpus chips. False leaves only the chips, for a deployment where a visitor
    # should start from a question. The composer buttons are not affected.
    start_screen_actions: bool = True
    # False takes Delete out of the chat altogether: the composer button, the start
    # screen chip and the delete actions. "Delete all" empties the collection the
    # chat answers from, including chunks that were loaded outside the app.
    delete_enabled: bool = True
    llm_provider: LlmProvider = "anthropic"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    bedrock_model: str = "amazon.nova-lite-v1:0"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    grove_api_key: SecretStr | None = None
    grove_model: str = "gpt-4o"
    grove_base_url: str | None = None
    skip_index_creation: bool = False
    skip_ingest: bool = False
    log_level: LogLevel = "INFO"
    demo_queries_path: Path = Path("assets/demo_queries.yaml")
    # Bundled corpus. The module renders assets/document_dirs with the caller's
    # files, so DOCUMENT_DIRS replaces this default for a caller that ingests
    # elsewhere. A caller with no corpus sets DOCUMENT_DIRS to an empty string.
    document_dirs: Annotated[list[Path], NoDecode] = Field(
        default_factory=lambda: [Path("assets/document_dirs")]
    )
    # Driver default is 30s, right for queries but too long for a health probe.
    mongo_server_selection_timeout_ms: int = 30_000

    @field_validator("document_dirs", mode="before")
    @classmethod
    def split_document_dirs(cls, value: object) -> object:
        match value:
            case str():
                return [Path(part) for part in value.split(os.pathsep) if part]
            case _:
                return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        match value:
            case str():
                return value.upper()
            case _:
                return value

    @field_validator("rag_system_prompt", mode="before")
    @classmethod
    def default_for_blank_prompt(cls, value: object) -> object:
        # A deployment without chatbot.system_prompt, or one that sets an empty
        # string, sends a blank value. An empty prompt would drop the answer
        # contract, so keep the built-in prompt in that case.
        match value:
            case str() if not value.strip():
                return DEFAULT_RAG_SYSTEM_PROMPT
            case _:
                return value

    @field_validator("chunk_max_tokens")
    @classmethod
    def validate_chunk_max_tokens(cls, value: int) -> int:
        if not MIN_CHUNK_MAX_TOKENS <= value <= MAX_CHUNK_MAX_TOKENS:
            msg = (
                f"chunk_max_tokens must be between {MIN_CHUNK_MAX_TOKENS} and "
                f"{MAX_CHUNK_MAX_TOKENS}, got {value}"
            )
            raise ValueError(msg)
        if value > AUTOEMBED_CONTEXT_TOKENS:
            msg = (
                f"chunk_max_tokens must not exceed the autoEmbed context window of "
                f"{AUTOEMBED_CONTEXT_TOKENS} tokens, got {value}"
            )
            raise ValueError(msg)
        return value

    @field_validator("mongodb_uri")
    @classmethod
    def validate_mongodb_uri(cls, value: SecretStr) -> SecretStr:
        uri = value.get_secret_value()
        if uri.startswith(("mongodb://", "mongodb+srv://")):
            return value
        msg = "mongodb_uri must start with mongodb:// or mongodb+srv://"
        raise ValueError(msg)


@lru_cache
def get_settings() -> HybridSearchSettings:
    return HybridSearchSettings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def apply_log_level(level: str) -> None:
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
