"""A permission dialog the user dismisses (Esc or decline) decides nothing: its Inbox entry
is cancelled — never rejected — at the next prompt or the session's end, and a dialog that
was allowed is forgotten because its tool answered the entry itself."""

import json

import _client
import post_tool
import pre_tool
import user_prompt

DECIDE = "mcp__plugin_relebo_relebo__relebo_decide_inbox"
SESSION = "sess-1"
GATE_CALL = {"entry_id": 18, "run_id": 7, "command": "git push", "tool_use_id": "tu-1", "via": "dialog"}
DECIDE_CALL = {"entry_id": 317, "run_id": 7, "tool": DECIDE, "tool_use_id": "tu-2", "via": "dialog"}
INBOX_PARKED = {"entry_id": 51, "run_id": 7, "command": "gh release create"}


class _Engine:
    """What the hooks tell the engine and keep in the session file, without disk or network."""

    def __init__(self, parked, statuses=None):
        self.parked = list(parked)
        self.statuses = statuses or {}
        self.answered = []

    def pending_approvals(self, session_id):
        return list(self.parked)

    def clear_pending_approval(self, session_id, entry_id):
        self.parked = [a for a in self.parked if a["entry_id"] != entry_id]

    def answer_approval(self, entry_id, decision):
        self.answered.append((entry_id, decision))
        return {"status": "cancelled" if decision == "cancel" else "approved"}

    def get(self, path):
        status = self.statuses.get(int(path.rsplit("/", 1)[1]))
        return {"status": status} if status else None


def _wire(monkeypatch, engine):
    for name in ("pending_approvals", "clear_pending_approval", "answer_approval", "get"):
        monkeypatch.setattr(_client, name, getattr(engine, name))


def _transcript(tmp_path, ended):
    """A transcript where each listed tool call already has its tool_result."""
    path = tmp_path / "transcript.jsonl"
    lines = [
        json.dumps({"message": {"content": [{"type": "tool_result", "tool_use_id": tool_use_id}]}})
        for tool_use_id in ended
    ]
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def test_a_dismissed_gate_dialog_cancels_its_entry_at_the_next_prompt(monkeypatch, tmp_path):
    engine = _Engine([GATE_CALL])
    _wire(monkeypatch, engine)
    lines = user_prompt._decided_approvals(SESSION, _transcript(tmp_path, ["tu-1"]))
    assert engine.answered == [(18, "cancel")]
    assert engine.parked == []
    assert len(lines) == 1 and "CANCELLED" in lines[0] and "git push" in lines[0]


def test_a_dialog_still_open_stays_parked(monkeypatch, tmp_path):
    engine = _Engine([GATE_CALL])
    _wire(monkeypatch, engine)
    assert user_prompt._decided_approvals(SESSION, _transcript(tmp_path, ["other"])) == []
    assert engine.answered == []
    assert engine.parked == [GATE_CALL]


def test_an_action_parked_on_the_inbox_is_never_cancelled_by_the_relay(monkeypatch, tmp_path):
    engine = _Engine([INBOX_PARKED])
    _wire(monkeypatch, engine)
    assert user_prompt._decided_approvals(SESSION, _transcript(tmp_path, [])) == []
    assert engine.answered == []


def test_a_dismissed_decide_dialog_cancels_the_proposal(monkeypatch, tmp_path):
    engine = _Engine([DECIDE_CALL])
    _wire(monkeypatch, engine)
    lines = user_prompt._decided_approvals(SESSION, _transcript(tmp_path, ["tu-2"]))
    assert engine.answered == [(317, "cancel")]
    assert engine.parked == []
    assert len(lines) == 1 and "CANCELLED" in lines[0] and "#317" in lines[0]


def test_an_allowed_decide_call_is_forgotten_not_cancelled(monkeypatch):
    engine = _Engine([DECIDE_CALL, GATE_CALL])
    _wire(monkeypatch, engine)
    post_tool._forget_decided_call(
        {"session_id": SESSION, "tool_use_id": "tu-2", "tool_input": {"entry_id": 317}}
    )
    assert engine.parked == [GATE_CALL]
    assert engine.answered == []


def test_the_session_end_cancels_only_the_dialogs_still_parked(monkeypatch):
    engine = _Engine([GATE_CALL, DECIDE_CALL, INBOX_PARKED])
    _wire(monkeypatch, engine)
    _client.cancel_dismissed_dialogs(SESSION)
    assert sorted(engine.answered) == [(18, "cancel"), (317, "cancel")]
    assert engine.parked == [INBOX_PARKED]


def test_the_decide_gate_parks_the_call_behind_the_dialog(monkeypatch, capsys):
    parked = []
    monkeypatch.setattr(_client, "record_pending_approval", lambda sid, a: parked.append((sid, a)))
    monkeypatch.setattr(_client, "session_run_id", lambda sid: 7)
    pre_tool._gate_decide(
        {"session_id": SESSION, "tool_use_id": "tu-2", "permission_mode": "default"},
        {"entry_id": 317, "decision": "approve"},
    )
    output = json.loads(capsys.readouterr().out)
    assert output["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert parked == [(SESSION, {
        "entry_id": 317, "run_id": 7, "tool": DECIDE, "summary": "approve Inbox entry #317",
        "tool_use_id": "tu-2", "via": "dialog",
    })]


def test_no_relay_ever_rejects():
    """Rejecting is the user's word in the Inbox or the dialog, never something a hook infers."""
    assert _client.DECISION_CANCEL == "cancel"
    for module in (user_prompt, post_tool, pre_tool):
        assert "_DECISION_REJECT" not in vars(module)
