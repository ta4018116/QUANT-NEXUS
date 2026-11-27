import json

from app.engine_event_store import EngineEventStore


def test_event_store_publishes_deduplicates_and_replays(tmp_path):
    store = EngineEventStore(str(tmp_path / "events.sqlite3"))
    first = store.publish(
        "opportunity",
        {"score": 88, "tier": "GOLD"},
        symbol="BTCUSDT",
        dedupe_key="BTCUSDT:15m:bar-1",
    )
    duplicate = store.publish(
        "opportunity",
        {"score": 99, "tier": "PLATINUM"},
        symbol="BTCUSDT",
        dedupe_key="BTCUSDT:15m:bar-1",
    )
    assert first["inserted"] is True
    assert duplicate["inserted"] is False
    assert duplicate["event_id"] == first["event_id"]
    events = store.list_events(event_type="opportunity", symbol="BTCUSDT")
    assert len(events) == 1
    assert events[0]["payload"]["score"] == 88
    stats = store.stats()
    assert stats["published"] == 1
    assert stats["consumed"] == 0
    assert stats["backlog"] == 1
    assert json.dumps(events, allow_nan=False)


def test_event_store_acknowledges_events_once(tmp_path):
    store = EngineEventStore(str(tmp_path / "events.sqlite3"))
    event = store.publish("audit", {"action": "analysis_run"}, symbol="ETHUSDT")
    assert store.acknowledge([event["event_id"]]) == 1
    assert store.acknowledge([event["event_id"]]) == 0
    assert store.stats()["consumed"] == 1


def test_event_store_rejects_non_json_numeric_payload(tmp_path):
    store = EngineEventStore(str(tmp_path / "events.sqlite3"))
    try:
        store.publish("bad", {"value": float("inf")})
    except ValueError:
        pass
    else:
        raise AssertionError("non-finite event payload must be rejected")
