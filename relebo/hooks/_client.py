"""Shared client for the Relebo session hooks: machine identity, engine HTTP,
offline spool and render cache. Stdlib only — hooks run on the system python3,
which can be 3.9: annotations stay postponed."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

_RELEBO_DIR = Path.home() / ".relebo"
_STATE_PATH = _RELEBO_DIR / "machine.json"
_SESSIONS_DIR = _RELEBO_DIR / "sessions"
_SPOOL_DIR = _RELEBO_DIR / "spool"
_RENDER_CACHE_DIR = _RELEBO_DIR / "render-cache"

_TIMEOUT_S = 8
SHADOW = "shadow"
ENFORCE = "enforce"
_GATE_MODE_DEFAULT = SHADOW


def _state() -> dict:
    if _STATE_PATH.exists():
        return json.loads(_STATE_PATH.read_text())
    return {}


def engine_url() -> str:
    return (
        _state().get("engine_url")
        or os.environ.get("CLAUDE_PLUGIN_OPTION_ENGINE_URL")
        or os.environ.get("RELEBO_ENGINE_URL")
        or "http://127.0.0.1:8100"
    ).rstrip("/")


def machine_key() -> str:
    return _state().get("fingerprint", "")


def gate_mode() -> str:
    return os.environ.get("CLAUDE_PLUGIN_OPTION_GATE_MODE") or _GATE_MODE_DEFAULT


def post(path: str, body: dict, timeout: float = _TIMEOUT_S) -> dict | None:
    """POST to the engine; None on any failure — hooks never raise."""
    key = machine_key()
    if not key:
        return None
    request = urllib.request.Request(
        f"{engine_url()}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Machine-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode() or "{}")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _session(claude_session_id: str) -> dict:
    path = _SESSIONS_DIR / f"{claude_session_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError:
        return {}


def session_run_id(claude_session_id: str) -> int | None:
    return _session(claude_session_id).get("run_id")


def session_gate_mode(claude_session_id: str) -> str:
    return _session(claude_session_id).get("gate_mode") or gate_mode()


def save_session(claude_session_id: str, run_id: int, mode: str) -> None:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (_SESSIONS_DIR / f"{claude_session_id}.json").write_text(
        json.dumps({"run_id": run_id, "gate_mode": mode})
    )


def spool_event(claude_session_id: str, event: dict) -> None:
    _SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    with (_SPOOL_DIR / f"{claude_session_id}.jsonl").open("a") as spool:
        spool.write(json.dumps(event) + "\n")


def flush_spool(claude_session_id: str, run_id: int) -> None:
    path = _SPOOL_DIR / f"{claude_session_id}.jsonl"
    if not path.exists():
        return
    remaining = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        if post(f"/machine/sessions/{run_id}/events", json.loads(line)) is None:
            remaining.append(line)
    if remaining:
        path.write_text("\n".join(remaining) + "\n")
    else:
        path.unlink()


def record_event(claude_session_id: str, kind: str, turn_key: str, payload: dict) -> None:
    event = {"kind": kind, "turn_key": turn_key, "payload": payload}
    run_id = session_run_id(claude_session_id)
    if run_id is None or post(f"/machine/sessions/{run_id}/events", event) is None:
        spool_event(claude_session_id, event)
    elif run_id is not None:
        flush_spool(claude_session_id, run_id)


def cache_renders(renders: list[dict]) -> None:
    _RENDER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for render in renders:
        name = f"{render['scope']}-{render['workspace_id']}"
        (_RENDER_CACHE_DIR / f"{name}.json").write_text(json.dumps(render))


def cached_renders() -> list[dict]:
    if not _RENDER_CACHE_DIR.exists():
        return []
    renders = []
    for path in sorted(_RENDER_CACHE_DIR.glob("*.json")):
        try:
            renders.append(json.loads(path.read_text()))
        except ValueError:
            continue
    # Personal precedence holds in the cache too.
    return sorted(renders, key=lambda r: (r.get("scope") != "personal", r.get("workspace_id")))
