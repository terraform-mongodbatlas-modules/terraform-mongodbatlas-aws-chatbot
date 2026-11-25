from __future__ import annotations

from hybrid_search.health import IndexState, build_health_payload


def test_payload_ready_with_data():
    payload = build_health_payload(
        index_states=[
            IndexState(name="autoembed_idx", status="READY"),
            IndexState(name="text_idx", status="READY"),
        ],
        has_chunks=True,
    )
    assert payload == {
        "indexes_ready": True,
        "data_ingested": True,
        "indexes": [
            {"name": "autoembed_idx", "status": "READY"},
            {"name": "text_idx", "status": "READY"},
        ],
    }


def test_payload_not_ready_when_one_building():
    payload = build_health_payload(
        index_states=[
            IndexState(name="autoembed_idx", status="BUILDING"),
            IndexState(name="text_idx", status="READY"),
        ],
        has_chunks=True,
    )
    assert payload["indexes_ready"] is False


def test_payload_empty_collection():
    payload = build_health_payload(
        index_states=[
            IndexState(name="autoembed_idx", status="READY"),
            IndexState(name="text_idx", status="READY"),
        ],
        has_chunks=False,
    )
    assert payload["indexes_ready"] is True
    assert payload["data_ingested"] is False


def test_payload_missing_index_is_missing():
    payload = build_health_payload(
        index_states=[
            IndexState(name="autoembed_idx", status="MISSING"),
            IndexState(name="text_idx", status="READY"),
        ],
        has_chunks=False,
    )
    assert payload["indexes_ready"] is False
    assert payload["indexes"][0] == {"name": "autoembed_idx", "status": "MISSING"}


def test_payload_carries_the_index_detail_when_present():
    payload = build_health_payload(
        index_states=[
            IndexState(
                name="autoembed_idx",
                status="FAILED",
                detail="autoEmbed model is not enabled",
            ),
            IndexState(name="text_idx", status="READY"),
        ],
        has_chunks=True,
    )
    assert payload["indexes"][0] == {
        "name": "autoembed_idx",
        "status": "FAILED",
        "detail": "autoEmbed model is not enabled",
    }
    assert payload["indexes"][1] == {"name": "text_idx", "status": "READY"}
