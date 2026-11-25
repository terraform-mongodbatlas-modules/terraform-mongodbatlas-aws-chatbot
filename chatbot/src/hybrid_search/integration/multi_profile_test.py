"""Two corpora in one registry: each profile keeps its own chips, prompt, and chunks.

Registers two corpus directories through ``register-corpus``, then checks that the
profile listing carries both documents and that a query against one collection
never returns the other corpus's file. Atlas Search indexes are eventually
consistent, so the query polls until its own corpus's file appears before the
isolation assertion runs.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from pymongo import MongoClient
from typer.testing import CliRunner

from hybrid_search.chatbot_profiles import PROFILES_COLLECTION
from hybrid_search.cli.app import app
from hybrid_search.integration.conftest import TEST_DATABASE, integration_settings
from hybrid_search.settings import clear_settings_cache
from hybrid_search.ui import profiles as profiles_module

COLLECTIONS = ("corpus_a", "corpus_b")
TERMS = {"corpus_a": "zorblatt", "corpus_b": "quuxington"}
POLL_TIMEOUT_S = 120
POLL_INTERVAL_S = 3
runner = CliRunner()


def _write_corpus(root: Path, collection: str, term: str) -> Path:
    corpus = root / collection
    docs = corpus / "docs"
    docs.mkdir(parents=True)
    (docs / f"{collection}.md").write_text(
        f"# {collection}\n\nThe {term} field appears in this corpus.\n" * 20
    )
    (corpus / "queries.yaml").write_text(f"- label: {collection}\n  message: What is the {term}?\n")
    (corpus / "system_prompt.txt").write_text(f"Answer as {collection}.")
    (corpus / "corpus.yaml").write_text(
        f"collection: {collection}\ndisplay_name: Corpus {collection[-1].upper()}\n"
    )
    return corpus


def _invoke(env: dict[str, str], args: list[str]):
    clear_settings_cache()
    return runner.invoke(app, args, env=env)


def _query(env: dict[str, str], collection: str, term: str) -> list[str]:
    result = _invoke(
        {**env, "CHUNKS_COLLECTION": collection},
        ["query", "--query", term, "--mode", "keyword", "--no-llm"],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["source_files"]


def _query_until_file(env: dict[str, str], collection: str, term: str) -> list[str]:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    sources: list[str] = []
    while time.monotonic() < deadline:
        sources = _query(env, collection, term)
        if any(f"{collection}.md" in source for source in sources):
            return sources
        time.sleep(POLL_INTERVAL_S)
    return sources


def _cleanup(uri: str) -> None:
    client = MongoClient(uri)
    try:
        database = client[TEST_DATABASE]
        for name in COLLECTIONS:
            database.drop_collection(name)
            database.drop_collection(f"{name}_ingest_state")
        database[PROFILES_COLLECTION].delete_many({"_id": {"$in": list(COLLECTIONS)}})
    finally:
        client.close()


def test_two_profiles_keep_their_own_chips_prompts_and_chunks(tmp_path: Path):
    settings = integration_settings()
    uri = settings.mongodb_uri.get_secret_value()
    _cleanup(uri)
    env = {"MONGODB_DATABASE": TEST_DATABASE}
    corpora = {
        collection: _write_corpus(tmp_path, collection, TERMS[collection])
        for collection in COLLECTIONS
    }
    try:
        for corpus in corpora.values():
            result = _invoke(env, ["register-corpus", "--corpus", str(corpus)])
            assert result.exit_code == 0, result.output

        profiles_module.clear_profile_cache()
        listing = asyncio.run(profiles_module.load_profile_listing(settings))
        by_collection = listing.by_collection()
        assert listing.profiles[0].default is True
        for collection in COLLECTIONS:
            profile = by_collection[collection]
            assert profile.display_name == f"Corpus {collection[-1].upper()}"
            assert [query.label for query in profile.queries] == [collection]
            assert profile.system_prompt == f"Answer as {collection}."

        sources_a = _query_until_file(env, "corpus_a", TERMS["corpus_a"])
        assert any("corpus_a.md" in source for source in sources_a), sources_a
        assert all("corpus_b.md" not in source for source in sources_a), sources_a

        sources_b = _query_until_file(env, "corpus_b", TERMS["corpus_b"])
        assert any("corpus_b.md" in source for source in sources_b), sources_b
        assert all("corpus_a.md" not in source for source in sources_b), sources_b
    finally:
        _cleanup(uri)
