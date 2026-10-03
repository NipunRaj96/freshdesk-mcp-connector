"""Real HTTP against mock_freshdesk.py (no credentials)."""
import asyncio
import threading

import pytest

import mock_freshdesk
import server


@pytest.fixture
def live(monkeypatch):
    srv = mock_freshdesk.serve(0, limit=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("FRESHDESK_BASE_URL", f"http://127.0.0.1:{srv.server_port}/api/v2")
    monkeypatch.setenv("FRESHDESK_API_KEY", mock_freshdesk.KEY)
    server._client = None
    yield srv
    srv.shutdown()
    server._client = None


def test_search_get_list_conversations(live):
    s = asyncio.run(server.search_tickets("status:2 AND priority:>2"))
    assert s["total"] > 0 and all(t["status"] == "open" for t in s["tickets"])
    tid = s["tickets"][0]["id"]
    t = asyncio.run(server.get_ticket(tid, include_conversations=True))["ticket"]
    assert "phone" not in t["requester"] and t["conversations"][1]["private"] is True
    assert len(asyncio.run(server.list_ticket_conversations(tid))["conversations"]) == 2
    assert asyncio.run(server.list_tickets(per_page=10))["has_more"] is True


def test_wrong_key_and_missing_ticket(live, monkeypatch):
    with pytest.raises(server.FreshdeskError, match="404"):
        asyncio.run(server.get_ticket(9999))
    monkeypatch.setenv("FRESHDESK_API_KEY", "wrong")
    server._client = None
    with pytest.raises(server.FreshdeskError, match="401"):
        asyncio.run(server.get_ticket(1))


def test_rate_limit_recovers_after_retry_after(monkeypatch):
    srv = mock_freshdesk.serve(0, limit=2, window=2)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("FRESHDESK_BASE_URL", f"http://127.0.0.1:{srv.server_port}/api/v2")
    monkeypatch.setenv("FRESHDESK_API_KEY", mock_freshdesk.KEY)
    server._client = None
    for _ in range(4):  # calls 3 and 4 get 429, sleep the real Retry-After, then succeed
        assert "tickets" in asyncio.run(server.list_tickets(per_page=1))
    srv.shutdown()
    server._client = None
