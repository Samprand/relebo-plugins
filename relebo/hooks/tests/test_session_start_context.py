"""Offline, the cached facts reach the session at start. Index mode leaves them to the
prompts that call for them, and no prompt is answered while the engine is unreachable."""

import session_start

RUBRIC = {
    "scope": "personal",
    "workspace_id": 2,
    "version": "0a32",
    "kind": "rubric",
    "content": "## [comments]\n_Applies when:_ writing a comment\nWhy, never what.",
}
FACTS = {
    "scope": "personal",
    "workspace_id": 2,
    "version": "b59c",
    "kind": "facts",
    "content": "- **Engine listens on 8100** — the desktop app starts it.",
}


def _index_mode(monkeypatch):
    monkeypatch.setattr(
        session_start._client, "rubric_context", lambda: session_start._client.RUBRIC_INDEX
    )


def test_online_index_mode_leaves_facts_to_the_prompts(monkeypatch):
    _index_mode(monkeypatch)
    context = session_start._context([RUBRIC, FACTS], stale=False, mode="enforce", project="Relebo")
    assert "loaded: rubric index personal · rules and facts arrive per prompt]" in context
    assert "- comments: writing a comment" in context
    assert "Engine listens on 8100" not in context


def test_stale_index_mode_injects_the_cached_facts(monkeypatch):
    _index_mode(monkeypatch)
    context = session_start._context([RUBRIC, FACTS], stale=True, mode="enforce", project=None)
    assert "loaded: rubric index personal, facts personal · STALE — engine unreachable]" in context
    assert "rules and facts arrive per prompt" not in context
    assert "[Relebo project facts — personal · vb59c]\n- **Engine listens on 8100**" in context
    assert "- comments: writing a comment" in context
