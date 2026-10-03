"""A pretend Freshdesk you can run on your own computer, so the connector can be tried without an account.

    uv run python mock_freshdesk.py [--port 8099] [--limit 0] [--window 60]

--limit N makes it answer "too many requests" after N calls within --window seconds (0 means never).
Search understands only simple conditions like status:2 or priority:>2, joined with AND.
"""
import argparse
import base64
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

KEY = "mock-key"  # the only API key the pretend server accepts
SUBJECTS = ["Refund not received", "Payment failed twice", "Settlement delayed", "Chargeback query",
            "Cannot download invoice", "Webhook not firing", "Change bank account", "KYC pending"]
TICKETS = [
    {"id": i, "subject": f"{SUBJECTS[i % 8]} #{i}", "status": 2 + i % 4, "priority": 1 + (i // 4) % 4,
     "requester_id": 1000 + i, "responder_id": 7 if i % 2 else None,
     "tags": ["refund"] if i % 3 == 0 else [], "type": "Question",
     "description_text": f"Customer {1000 + i} reports: {SUBJECTS[i % 8].lower()}." + (f" Payment pay_29QQoUBi66x{i:03d} is affected." if i % 5 == 0 else ""),
     "created_at": f"2026-09-{1 + i % 28:02d}T09:00:00Z", "updated_at": f"2026-09-{1 + i % 28:02d}T10:00:00Z",
     "due_by": f"2026-10-{1 + i % 28:02d}T09:00:00Z"}
    for i in range(1, 46)
]
CONVS = lambda tid: [  # noqa: E731
    {"id": tid * 10, "from_email": f"c{tid}@example.com", "private": False, "incoming": True,
     "body_text": "Please help, still not resolved.", "created_at": "2026-09-02T11:00:00Z"},
    {"id": tid * 10 + 1, "from_email": "agent@example.com", "private": True, "incoming": False,
     "body_text": "Internal: check with settlements team.", "created_at": "2026-09-02T12:00:00Z"},
]
hits = []


def match(t, clause):
    field, _, rest = clause.partition(":")
    op = "="
    if rest[:1] in "<>":
        op, rest = rest[0], rest[1:]
    rest = rest.strip("'")
    v = t.get(field.strip())
    if field.strip() == "tag":
        return rest in t["tags"]
    if v is None:
        return False
    v = str(v)
    return v == rest if op == "=" else (v > rest if op == ">" else v < rest)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body=None, headers=None):
        data = json.dumps(body if body is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        want = "Basic " + base64.b64encode(f"{KEY}:X".encode()).decode()
        if auth != want:
            return self.send(401, {"code": "invalid_credentials"})
        now = time.time()
        hits[:] = [h for h in hits if now - h < self.server.window]
        limit = self.server.limit
        if limit and len(hits) >= limit:
            return self.send(429, {"message": "rate limited"}, {"Retry-After": str(int(hits[0] + self.server.window - now) + 1)})
        hits.append(now)
        rl = {"X-RateLimit-Remaining": str(max(limit - len(hits), 0)) if limit else "3000"}
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = u.path.removeprefix("/api/v2").strip("/").split("/")
        page, per = int(q.get("page", 1)), int(q.get("per_page", 30))
        if parts == ["search", "tickets"]:
            clauses = [c.strip() for c in q["query"].strip('"').split(" AND ")]
            found = [t for t in TICKETS if all(match(t, c) for c in clauses)]
            return self.send(200, {"total": len(found), "results": found[(page - 1) * 30: page * 30]}, rl)
        if parts == ["tickets"]:
            found = TICKETS
            if "email" in q:
                found = [t for t in found if f"c{t['requester_id'] - 1000}@example.com" == q["email"]]
            chunk = found[(page - 1) * per: page * per]
            more = page * per < len(found)
            return self.send(200, chunk, {**rl, **({"Link": '<x>; rel="next"'} if more else {})})
        if len(parts) >= 2 and parts[0] == "tickets" and parts[1].isdigit():
            t = next((t for t in TICKETS if t["id"] == int(parts[1])), None)
            if not t:
                return self.send(404, {"message": "not found"})
            if len(parts) == 3 and parts[2] == "conversations":
                return self.send(200, CONVS(t["id"]), rl)
            full = dict(t, requester={"name": f"Customer {t['id']}", "email": f"c{t['id']}@example.com", "phone": "x"},
                        stats={"first_responded_at": None})
            if "conversations" in q.get("include", ""):
                full["conversations"] = CONVS(t["id"])
            return self.send(200, full, rl)
        self.send(404, {"message": "unknown route"})


def serve(port=0, limit=0, window=60):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.limit = limit
    srv.window = window
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--window", type=int, default=60)
    a = ap.parse_args()
    print(f"mock Freshdesk on http://127.0.0.1:{a.port}/api/v2  key={KEY}")
    serve(a.port, a.limit, a.window).serve_forever()
