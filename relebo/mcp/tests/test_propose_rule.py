"""The propose tool carries a full proposal to the engine and hands back the one-line
marker the message ends with; a system rule names the maintainers, a personal one the
user's Inbox, and a missing field never leaves the machine."""

import server
from _rule_scope import RuleScopeE

FIELDS = dict(
    anchor="review-in-judge-sized-slices",
    applies_when="the user asks to review a diff",
    rule="Split the review into slices of at most twelve files.",
    why="The judge reads at most twelve files per turn.",
    violation="One turn reviewing the whole working tree.",
)


def _engine(monkeypatch, filed, sessions_dir):
    calls = []

    def request(method, path, body=None):
        calls.append((method, path, body))
        return filed

    monkeypatch.setattr(server, "_request", request)
    monkeypatch.setattr(server, "_SESSIONS_DIR", sessions_dir)
    (sessions_dir / "s.json").write_text('{"run_id": 188}')
    return calls


def test_a_system_rule_is_posted_with_the_system_section_and_returns_the_marker(
    monkeypatch, tmp_path
):
    calls = _engine(
        monkeypatch,
        [{"inbox_entry_id": 350, "anchor": FIELDS["anchor"], "title": "t", "scope": "system"}],
        tmp_path,
    )
    result = server.relebo_propose_rule(**FIELDS, scope=RuleScopeE.SYSTEM)
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/machine/sessions/188/proposals")
    assert body["section"] == "system"
    assert body["candidate"].splitlines() == [
        f"- **Rule:** {FIELDS['rule']}",
        f"- **Why:** {FIELDS['why']}",
        f"- **Violation looks like:** {FIELDS['violation']}",
    ]
    assert result["marker"] == "Rubric addition (system) [review-in-judge-sized-slices]"
    assert "maintainers" in result["note"]


def test_a_personal_rule_names_the_users_inbox(monkeypatch, tmp_path):
    calls = _engine(monkeypatch, [{"inbox_entry_id": 351, "anchor": "x", "title": "t"}], tmp_path)
    result = server.relebo_propose_rule(**FIELDS)
    assert calls[0][2]["section"] == "personal rubric"
    assert result["marker"] == "Rubric addition (personal) [review-in-judge-sized-slices]"
    assert "Inbox" in result["note"]


def test_nothing_filed_has_no_marker(monkeypatch, tmp_path):
    _engine(monkeypatch, [], tmp_path)
    result = server.relebo_propose_rule(**FIELDS)
    assert result["marker"] is None and "duplicate" in result["note"]


def test_a_missing_field_never_reaches_the_engine(monkeypatch, tmp_path):
    calls = _engine(monkeypatch, [], tmp_path)
    result = server.relebo_propose_rule(**{**FIELDS, "why": "  "})
    assert "required" in result["error"] and calls == []
