from datetime import datetime, timedelta, timezone

from app.main import _heartbeat_age_seconds


def test_missing_or_invalid_heartbeat_is_unknown_not_fresh():
    now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    assert _heartbeat_age_seconds(None, now) is None
    assert _heartbeat_age_seconds("not-a-timestamp", now) is None


def test_heartbeat_age_uses_recorded_completion_timestamp():
    now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    stamp = (now - timedelta(seconds=95)).isoformat()
    assert _heartbeat_age_seconds(stamp, now) == 95.0
