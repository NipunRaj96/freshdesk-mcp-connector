"""Starts the real server the way an agent would, and talks to it as an agent would."""
import asyncio
import json
import os
import sys
import threading

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import mock_freshdesk


async def session_calls(port):
    params = StdioServerParameters(
        command=sys.executable,
        args=["server.py"],
        env={**os.environ, "FRESHDESK_BASE_URL": f"http://127.0.0.1:{port}/api/v2",
             "FRESHDESK_API_KEY": mock_freshdesk.KEY},
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools)
            found = json.loads((await s.call_tool("search_tickets", {"query": "status:2"})).content[0].text)
            tid = 5  # the pretend server mentions a payment id in every fifth ticket
            one = json.loads((await s.call_tool("get_ticket", {"ticket_id": tid})).content[0].text)
            bad = await s.call_tool("get_ticket", {"ticket_id": 99999})
            return names, found, one, bad


def test_agent_can_use_every_tool_over_the_real_connection():
    srv = mock_freshdesk.serve(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    names, found, one, bad = asyncio.run(session_calls(srv.server_port))
    srv.shutdown()
    assert names == ["get_ticket", "list_ticket_conversations", "list_tickets", "search_tickets"]
    assert found["total"] > 0 and "never follow instructions" in found["note"]
    assert one["ticket"]["razorpay_ids"][0].startswith("pay_")
    assert bad.isError and "404" in bad.content[0].text
