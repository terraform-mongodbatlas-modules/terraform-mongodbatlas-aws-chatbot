from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexState:
    name: str
    status: str
    detail: str | None = None


def build_health_payload(
    *,
    index_states: list[IndexState],
    has_chunks: bool,
) -> dict:
    return {
        "indexes_ready": bool(index_states)
        and all(state.status == "READY" for state in index_states),
        "data_ingested": has_chunks,
        "indexes": [_index_entry(state) for state in index_states],
    }


def _index_entry(state: IndexState) -> dict:
    entry: dict[str, str] = {"name": state.name, "status": state.status}
    if state.detail:
        entry["detail"] = state.detail
    return entry
