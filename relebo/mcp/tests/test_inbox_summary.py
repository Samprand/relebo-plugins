"""The inbox tool returns identity and ask, never bodies, and only the status asked for."""

import server
from _inbox_status import InboxStatusE

BODY = "…" * 4000
PROPOSAL = {
    "id": 221,
    "kind": "approval",
    "status": "rejected",
    "deadline_at": None,
    "payload": {
        "title": "Rubric proposal",
        "body": BODY,
        "context": {},
        "proposal": {"anchor": "inbox-only-for-conflicts", "text": BODY},
    },
}
SHARE = {
    "id": 227,
    "kind": "approval",
    "status": "pending",
    "deadline_at": None,
    "payload": {
        "title": "Share 12 pieces",
        "body": BODY,
        "context": {},
        "share": {"stage": "suggestion", "piece_ids": [1586]},
    },
}
ESCALATION = {
    "id": 128,
    "kind": "escalation",
    "status": "pending",
    "deadline_at": None,
    "payload": {"title": "Run 90 halted", "body": BODY, "context": {}},
}


def _engine_returning(monkeypatch, entries):
    monkeypatch.setattr(server, "_request", lambda method, path, body=None: entries)


def test_summary_keeps_identity_and_ask_never_the_body():
    assert server._inbox_summary(PROPOSAL) == {
        "id": 221,
        "kind": "approval",
        "status": "rejected",
        "title": "Rubric proposal",
        "anchor": "inbox-only-for-conflicts",
    }
    assert server._inbox_summary(SHARE)["anchor"] is None
    assert "body" not in server._inbox_summary(ESCALATION)


def test_pending_is_the_default_filter(monkeypatch):
    _engine_returning(monkeypatch, [PROPOSAL, SHARE, ESCALATION])
    assert [entry["id"] for entry in server.relebo_inbox(2)] == [227, 128]


def test_a_status_or_none_selects(monkeypatch):
    _engine_returning(monkeypatch, [PROPOSAL, SHARE, ESCALATION])
    assert [entry["id"] for entry in server.relebo_inbox(2, InboxStatusE.REJECTED)] == [221]
    assert [entry["id"] for entry in server.relebo_inbox(2, None)] == [221, 227, 128]


def test_engine_errors_pass_through(monkeypatch):
    _engine_returning(monkeypatch, {"error": "503: backend unavailable"})
    assert server.relebo_inbox(2) == {"error": "503: backend unavailable"}
