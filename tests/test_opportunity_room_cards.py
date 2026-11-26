from fastapi.testclient import TestClient

from app.main import app


def test_opportunity_room_renders_rich_cards_with_confirmation_and_watch_actions():
    client = TestClient(app)
    response = client.get("/static/monitoring-room.js")
    assert response.status_code == 200
    script = response.text
    assert "qn-opp-details" in script
    assert "turnover24h" in script
    assert "change24h" in script
    assert "entryConfirmation" in script
    assert "button.dataset.oppAction==='analyze'" in script
    assert "button.dataset.oppAction==='remove'" in script
    assert "removeMonitoringSymbol" in script
    assert "live_trading_enabled" not in script or "paper" in script.lower()


def test_opportunity_room_keeps_existing_watchlist_and_paper_only_guard():
    client = TestClient(app)
    room = client.get("/static/monitoring-room.js")
    health = client.get("/health").json()
    assert room.status_code == 200
    assert "quantNexusManualWatchlist" in room.text
    assert "addMonitoringSymbol" in room.text
    assert health["trading_mode"] == "simulation"
    assert health["live_trading_enabled"] is False



def test_monitoring_watchlist_renders_entry_plan_and_animated_progress_cards():
    client = TestClient(app)
    response = client.get("/static/monitoring-room.js")
    assert response.status_code == 200
    script = response.text
    assert "room-watch-card" in script
    assert "دخول مرجعي" in script
    assert "وقف الخسارة" in script
    assert "الهدف الأول" in script
    assert "الهدف الثاني" in script
    assert "room-progress-track" in script
    assert "roomProgressShimmer" in script
    assert "prefers-reduced-motion" in script


def test_monitoring_room_watchlist_renders_entry_details_and_animated_progress_cards():
    client = TestClient(app)
    response = client.get("/static/monitoring-room.js")
    assert response.status_code == 200
    script = response.text
    assert "room-watch-card" in script
    assert "دخول مرجعي" in script
    assert "وقف الخسارة" in script
    assert "الهدف الأول" in script
    assert "الهدف الثاني" in script
    assert "room-progress-track" in script
    assert "roomProgressShimmer" in script
    assert "prefers-reduced-motion" in script


def test_auto_paper_entry_requires_fresh_confirmed_setup(monkeypatch):
    import app.main as main

    async def fake_klines(symbol, category, interval, limit):
        return [["0", "100", "101", "99", "100", "1000"]] * 60, "TEST"

    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    monkeypatch.setattr(main, "analyze_klines", lambda rows: {
        "price": 100.0, "entry": 100.0, "stopLoss": 98.0, "target2": 104.0,
        "score": 99, "direction": "LONG"
    })
    monkeypatch.setattr(main, "evaluate_entry", lambda analysis: {
        "state": "APPROACH", "confirmed": False, "progress": 65,
        "reason": "شروط الشمعة المكتملة غير مكتملة"
    })
    client = TestClient(main.app)
    response = client.post("/api/paper/auto-entry/TESTUSDT?category=spot&interval=15m")
    assert response.status_code == 200
    payload = response.json()
    assert payload["opened"] is False
    assert payload["state"] == "APPROACH"
    assert payload["live_trading_enabled"] is False


def test_monitoring_room_connects_watchlist_to_paper_auto_monitor():
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    response = client.get("/static/monitoring-room.js")
    assert response.status_code == 200
    assert "/api/paper/auto-entry/" in response.text
    assert "/api/paper/monitor" in response.text
    assert "quantNexusManualWatchlist" in response.text
    assert "setInterval(cycle,20000)" in response.text
