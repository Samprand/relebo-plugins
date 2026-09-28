"""A prompt's ledger entry and its recall travel side by side and the turn needs both: a
request that fails is sent once more, the hook answers only when both are in, and a ledger
entry the engine still refuses waits in the spool."""

import io
import json
import threading
import time

import _client
import user_prompt

SESSION, RUN = "session-1", 272
PAYLOAD = {"session_id": SESSION, "cwd": "/repo", "prompt": "por qué falla el deploy"}


def _prepare(monkeypatch, posts):
    """A machine key and a run so the hook talks to the engine; every post goes to `posts`."""
    monkeypatch.setattr(_client, "machine_key", lambda: "fp")
    monkeypatch.setattr(_client, "session_run_id", lambda session_id: RUN)
    monkeypatch.setattr(_client, "ensure_session", lambda session_id, cwd: RUN)
    monkeypatch.setattr(_client, "touch_session", lambda session_id: None)
    monkeypatch.setattr(_client, "flush_spool", lambda session_id, run_id: None)
    monkeypatch.setattr(_client, "mark_served", lambda session_id, anchors: None)
    monkeypatch.setattr(_client, "rubric_context", lambda: _client.RUBRIC_INDEX)
    monkeypatch.setattr(_client, "_post_once", posts)


def _run(monkeypatch, capsys) -> dict:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(PAYLOAD)))
    user_prompt.main()
    out = capsys.readouterr().out
    return json.loads(out) if out else {}


def test_the_ledger_entry_and_the_recall_travel_side_by_side(monkeypatch, capsys):
    started: dict[str, float] = {}
    ended: dict[str, float] = {}

    def posts(path, body, key, timeout):
        name = path.rsplit("/", 1)[1]
        started[name] = time.perf_counter()
        time.sleep(0.2)
        ended[name] = time.perf_counter()
        return {"rules": ["## [a]\nrule"]} if name == "recall" else {"ok": True}

    _prepare(monkeypatch, posts)
    out = _run(monkeypatch, capsys)
    assert "## [a]" in out["hookSpecificOutput"]["additionalContext"]
    # Both started before either ended: they overlapped instead of queueing.
    assert max(started.values()) < min(ended.values())


def test_a_request_that_fails_once_is_sent_again(monkeypatch, capsys):
    calls: list[str] = []
    lock = threading.Lock()

    def posts(path, body, key, timeout):
        name = path.rsplit("/", 1)[1]
        with lock:
            calls.append(name)
            first = calls.count(name) == 1
        if first:
            return None
        return {"rules": ["## [a]\nrule"]} if name == "recall" else {"ok": True}

    spooled: list[dict] = []
    monkeypatch.setattr(_client, "spool_event", lambda session_id, event: spooled.append(event))
    _prepare(monkeypatch, posts)
    out = _run(monkeypatch, capsys)
    assert sorted(calls) == ["events", "events", "recall", "recall"]
    assert "## [a]" in out["hookSpecificOutput"]["additionalContext"]
    assert spooled == []


def test_a_ledger_entry_the_engine_keeps_refusing_waits_in_the_spool(monkeypatch, capsys):
    def posts(path, body, key, timeout):
        return None if path.endswith("/events") else {"rules": []}

    spooled: list[dict] = []
    monkeypatch.setattr(_client, "spool_event", lambda session_id, event: spooled.append(event))
    _prepare(monkeypatch, posts)
    _run(monkeypatch, capsys)
    [event] = spooled
    assert event["kind"] == "user_prompt" and event["payload"]["prompt"] == PAYLOAD["prompt"]
