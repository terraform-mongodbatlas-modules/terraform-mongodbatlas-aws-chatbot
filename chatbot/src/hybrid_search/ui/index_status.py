from __future__ import annotations

from hybrid_search.health import IndexState

READY = "READY"
FAILED = "FAILED"


def render_index_status(states: list[IndexState], *, collection: str) -> str:
    return "\n".join(f"{collection}.{state.name} {state.status}" for state in states)


def not_ready_names(states: list[IndexState]) -> list[str]:
    return [state.name for state in states if state.status != READY]


def failed_names(states: list[IndexState]) -> list[str]:
    return [state.name for state in states if state.status == FAILED]


def problem_message(states: list[IndexState], *, query: bool, collection: str) -> str | None:
    """Return the status message to show when an index is not READY, else None.

    `query` picks the not-ready wording: a query is blocked, a session can still open.
    `collection` names the selected chat profile's chunks collection, so the status
    block never reports a namespace the visitor is not querying.
    """
    if failed_names(states):
        detail = "Search is unavailable: an index failed."
        return f"{detail}\n\n{_status_block(states, collection=collection)}"
    if not_ready_names(states):
        detail = (
            "Indexes are not ready yet, so search would return nothing."
            if query
            else "Indexes are still building. Search may return no results until they are ready."
        )
        return f"{detail}\n\n{_status_block(states, collection=collection)}"
    return None


def _status_block(states: list[IndexState], *, collection: str) -> str:
    return f"```\n{render_index_status(states, collection=collection)}\n```"
