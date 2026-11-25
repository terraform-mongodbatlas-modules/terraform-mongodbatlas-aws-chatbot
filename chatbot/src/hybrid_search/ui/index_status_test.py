from __future__ import annotations

import pytest

from hybrid_search.chatbot_profiles import StartupStatus
from hybrid_search.health import IndexState
from hybrid_search.ui.index_status import (
    failed_names,
    not_ready_names,
    problem_message,
    render_index_status,
)


def _states(*statuses: str) -> list[IndexState]:
    names = ["autoembed_idx", "text_idx"]
    return [IndexState(name=name, status=status) for name, status in zip(names, statuses)]


def test_render_ready_lines():
    text = render_index_status(_states("READY", "READY"), collection="chunks")
    assert text == "chunks.autoembed_idx READY\nchunks.text_idx READY"


def test_render_building_line():
    states = _states("BUILDING", "READY")
    assert "chunks.autoembed_idx BUILDING" in render_index_status(states, collection="chunks")
    assert not_ready_names(states) == ["autoembed_idx"]
    assert failed_names(states) == []


def test_render_failed_line():
    states = _states("FAILED", "READY")
    assert "chunks.autoembed_idx FAILED" in render_index_status(states, collection="chunks")
    assert failed_names(states) == ["autoembed_idx"]
    assert not_ready_names(states) == ["autoembed_idx"]


def test_problem_message_none_when_ready():
    assert problem_message(_states("READY", "READY"), query=True, collection="chunks") is None
    assert problem_message(_states("READY", "READY"), query=False, collection="chunks") is None


def test_problem_message_failed_is_error():
    message = problem_message(_states("FAILED", "READY"), query=True, collection="chunks")
    assert message is not None
    assert "unavailable" in message
    assert "chunks.autoembed_idx FAILED" in message


def test_problem_message_not_ready_wording_differs_for_query():
    states = _states("BUILDING", "READY")
    query_message = problem_message(states, query=True, collection="chunks")
    session_message = problem_message(states, query=False, collection="chunks")
    assert query_message is not None and "not ready yet" in query_message
    assert session_message is not None and "still building" in session_message
    assert "chunks.autoembed_idx BUILDING" in query_message


@pytest.mark.parametrize("query", [True, False])
def test_problem_message_names_the_selected_collection(query: bool):
    message = problem_message(_states("BUILDING", "READY"), query=query, collection="health")

    assert message is not None
    assert "health.autoembed_idx BUILDING" in message
    assert "chunks.autoembed_idx" not in message


@pytest.mark.parametrize("query", [True, False])
def test_problem_message_missing_shows_the_recreate_command(query: bool):
    message = problem_message(_states("MISSING", "READY"), query=query, collection="chunks")

    assert message is not None
    assert "may still be starting" in message
    assert "hybrid-search index-create --recreate" in message


def test_problem_message_appends_the_recorded_startup_error():
    startup = StartupStatus(outcome="failed", phase="indexes", error="model is not enabled")

    message = problem_message(
        _states("MISSING", "READY"),
        query=True,
        collection="chunks",
        startup=startup,
    )

    assert message is not None
    assert "Startup failed during indexes: model is not enabled" in message


def test_problem_message_ignores_a_recorded_success():
    startup = StartupStatus(outcome="ok", phase="ingest")

    message = problem_message(
        _states("MISSING", "READY"),
        query=False,
        collection="chunks",
        startup=startup,
    )

    assert message is not None
    assert "Startup failed" not in message
