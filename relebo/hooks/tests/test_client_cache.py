"""Cached renders come back in the engine's order, system first, whatever the file names
sort to; a scope the cache does not know goes last."""

import json

import _client


def _cache(monkeypatch, tmp_path, renders):
    monkeypatch.setattr(_client, "_RENDER_CACHE_DIR", tmp_path)
    _client.cache_renders(renders)


def test_cached_renders_keep_system_personal_shared_order(monkeypatch, tmp_path):
    _cache(
        monkeypatch,
        tmp_path,
        [
            {"scope": "shared", "workspace_id": 6, "version": "c", "content": "team"},
            {"scope": "personal", "workspace_id": 2, "version": "b", "content": "mine"},
            {"scope": "system", "workspace_id": 9, "version": "a", "content": "everyone"},
            {"scope": "personal", "workspace_id": 2, "version": "f", "content": "facts", "kind": "facts"},
        ],
    )
    cached = _client.cached_renders()
    assert [(r["scope"], r["workspace_id"]) for r in cached] == [
        ("system", 9),
        ("personal", 2),
        ("personal", 2),
        ("shared", 6),
    ]
    assert json.loads((tmp_path / "system-9-rubric.json").read_text())["content"] == "everyone"


def test_an_unknown_scope_sorts_last(monkeypatch, tmp_path):
    _cache(
        monkeypatch,
        tmp_path,
        [
            {"scope": "future", "workspace_id": 1, "version": "z", "content": "?"},
            {"scope": "shared", "workspace_id": 6, "version": "c", "content": "team"},
        ],
    )
    assert [r["scope"] for r in _client.cached_renders()] == ["shared", "future"]
