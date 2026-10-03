"""Runs offline: Freshdesk is faked with httpx.MockTransport."""
import asyncio

import httpx
import pytest

import server


def fake(handler):
    server._client = httpx.AsyncClient(
        base_url="https://acme.freshdesk.com/api/v2", transport=httpx.MockTransport(handler)
    )
    server._last_remaining = None


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    waits = []

    async def fake_sleep(s):
        waits.append(s)

    monkeypatch.setattr(server.asyncio, "sleep", fake_sleep)
    return waits


def run(coro):
    return asyncio.run(coro)


def test_search_quotes_query_and_maps_codes():
    seen = {}

    def h(req):
        seen["q"] = req.url.params["query"]
        return httpx.Response(200, json={"total": 45, "results": [{"id": 1, "status": 2, "priority": 4}]})

    fake(h)
    out = run(server.search_tickets("status:2 AND priority:4"))
    assert seen["q"] == '"status:2 AND priority:4"'
    assert out["tickets"][0]["status"] == "open" and out["tickets"][0]["priority"] == "urgent"
    assert out["has_more"] is True


def test_search_rejects_bad_query_and_page():
    fake(lambda r: httpx.Response(500))
    with pytest.raises(server.FreshdeskError):
        run(server.search_tickets('tag:"x"'))
    with pytest.raises(server.FreshdeskError):
        run(server.search_tickets("status:2", page=11))


def test_429_honours_retry_after_then_succeeds(no_sleep):
    calls = []

    def h(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=[], headers={"X-RateLimit-Remaining": "41"})

    fake(h)
    out = run(server.list_tickets())
    assert len(calls) == 3 and no_sleep == [7.0, 7.0]
    assert out["rate_limit_remaining"] == 41


def test_429_gives_up_and_caps_wait(no_sleep):
    fake(lambda r: httpx.Response(429, headers={"Retry-After": "9999"}))
    with pytest.raises(server.FreshdeskError, match="rate limit"):
        run(server.list_tickets())
    assert max(no_sleep) == server.MAX_WAIT


def test_auth_and_not_found_errors_hide_nothing_sensitive():
    fake(lambda r: httpx.Response(401))
    with pytest.raises(server.FreshdeskError, match="401"):
        run(server.get_ticket(1))
    fake(lambda r: httpx.Response(404))
    with pytest.raises(server.FreshdeskError, match="404"):
        run(server.get_ticket(999))


def test_get_ticket_clips_long_body_and_flags_private_notes():
    t = {
        "id": 5,
        "status": 3,
        "description_text": "x" * 5000,
        "requester": {"name": "A", "email": "a@x.com", "phone": "SECRET"},
        "conversations": [{"id": 9, "private": True, "body_text": "internal"}],
    }
    fake(lambda r: httpx.Response(200, json=t))
    out = run(server.get_ticket(5, include_conversations=True))["ticket"]
    assert "truncated" in out["description"]
    assert out["requester"] == {"name": "A", "email": "a@x.com"}
    assert out["conversations"][0]["private"] is True


def test_list_has_more_from_link_header():
    fake(lambda r: httpx.Response(200, json=[], headers={"Link": '<https://x/?page=2>; rel="next"'}))
    assert run(server.list_tickets())["has_more"] is True


def test_only_get_requests_sent():
    methods = set()

    def h(req):
        methods.add(req.method)
        return httpx.Response(200, json=[])

    fake(h)
    run(server.list_tickets())
    run(server.list_ticket_conversations(1))
    assert methods == {"GET"}
