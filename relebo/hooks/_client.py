"""Shared client for the Relebo session hooks: machine identity, engine HTTP,
offline spool and render cache. Stdlib only — hooks run on the system python3,
which can be 3.9: annotations stay postponed."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

_RELEBO_DIR = Path.home() / ".relebo"
_STATE_PATH = _RELEBO_DIR / "machine.json"
_SESSIONS_DIR = _RELEBO_DIR / "sessions"
_SPOOL_DIR = _RELEBO_DIR / "spool"
_RENDER_CACHE_DIR = _RELEBO_DIR / "render-cache"

_ORPHAN_IDLE_S = 2 * 60 * 60
_TIMEOUT_S = 60
SHADOW = "shadow"
ENFORCE = "enforce"
_GATE_MODE_DEFAULT = SHADOW
RUBRIC_FULL = "full"
RUBRIC_INDEX = "index"
_RUBRIC_CONTEXT_DEFAULT = RUBRIC_INDEX
SOURCE_COMPACT = "compact"
# The stop gate's transcript cursor lives next to the session file, same directory.
CURSOR_SUFFIX = ".cursor.json"


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


def rubric_context() -> str:
    """full: the whole rubric and the facts block at session start. index: a one-line
    index per rule at start, the sections and facts each turn calls for on every prompt."""
    return os.environ.get("CLAUDE_PLUGIN_OPTION_RUBRIC_CONTEXT") or _RUBRIC_CONTEXT_DEFAULT


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


def get(path: str, timeout: float = _TIMEOUT_S) -> dict | None:
    """GET from the engine; None on any failure — hooks never raise."""
    key = machine_key()
    if not key:
        return None
    request = urllib.request.Request(
        f"{engine_url()}{path}", headers={"X-Machine-Key": key}, method="GET"
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


def open_session(claude_session_id: str, cwd: str, source: str) -> dict | None:
    """Register the session as a run on the engine and remember it locally; None when
    the engine is unreachable. The renders come back for the caller to inject."""
    import _git  # noqa: PLC0415 — hooks share one flat directory

    mode = gate_mode()
    compact = source == SOURCE_COMPACT
    session = post(
        "/machine/sessions",
        {
            "claude_session_id": claude_session_id,
            "cwd": cwd,
            "git_remote": _git.run(cwd, "remote", "get-url", "origin").strip() if cwd else "",
            "source": source,
            "gate_mode": mode,
            # A compaction goes on with its run: the ledger of prompts and approvals stays.
            "run_id": session_run_id(claude_session_id) if compact else None,
        },
    )
    if session is None:
        return None
    save_session(claude_session_id, session["run_id"], mode)
    if not compact:
        # A compaction lands mid-turn: the turn base must keep the turn's earlier changes.
        save_turn_base(claude_session_id, _git.snapshot(cwd))
    cache_renders(session["renders"])
    flush_spool(claude_session_id, session["run_id"])
    return session


def ensure_session(claude_session_id: str, cwd: str) -> int | None:
    """The run for this session, reopening one when it was closed as an orphan while
    the session sat idle: a live session is supervised until the user says otherwise."""
    run_id = session_run_id(claude_session_id)
    if run_id is not None:
        return run_id
    session = open_session(claude_session_id, cwd, "resume")
    return session["run_id"] if session else None


def save_session(claude_session_id: str, run_id: int, mode: str) -> None:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    # Merge: the turn base and parked approvals of a session outlive a compaction.
    state = _session(claude_session_id)
    state.update({"run_id": run_id, "gate_mode": mode})
    (_SESSIONS_DIR / f"{claude_session_id}.json").write_text(json.dumps(state))


def save_turn_base(claude_session_id: str, base: dict) -> None:
    """Where the current turn starts in the working tree: the gate diffs against it."""
    path = _SESSIONS_DIR / f"{claude_session_id}.json"
    if not path.exists():
        return
    state = _session(claude_session_id)
    state["turn_base"] = base
    path.write_text(json.dumps(state))


def turn_base(claude_session_id: str) -> dict:
    return _session(claude_session_id).get("turn_base") or {}


def record_pending_approval(claude_session_id: str, approval: dict) -> None:
    """An action parked on an Inbox decision the human has not taken yet; the next prompt
    checks it, so an approval given hours later still gets acted on."""
    path = _SESSIONS_DIR / f"{claude_session_id}.json"
    if not path.exists():
        return
    state = _session(claude_session_id)
    pending = [a for a in state.get("pending_approvals") or [] if a.get("entry_id") != approval.get("entry_id")]
    pending.append(approval)
    state["pending_approvals"] = pending
    path.write_text(json.dumps(state))


def pending_approvals(claude_session_id: str) -> list:
    return _session(claude_session_id).get("pending_approvals") or []


def answer_approval(entry_id: int, decision: str) -> dict | None:
    """Relays the user's answer in Claude Code's permission dialog to the Inbox entry."""
    return post(f"/machine/approvals/{entry_id}/answer", {"decision": decision})


def clear_pending_approval(claude_session_id: str, entry_id: int) -> None:
    path = _SESSIONS_DIR / f"{claude_session_id}.json"
    if not path.exists():
        return
    state = _session(claude_session_id)
    state["pending_approvals"] = [
        a for a in state.get("pending_approvals") or [] if a.get("entry_id") != entry_id
    ]
    path.write_text(json.dumps(state))


def touch_session(claude_session_id: str) -> None:
    path = _SESSIONS_DIR / f"{claude_session_id}.json"
    if path.exists():
        os.utime(path)


def close_orphans(current_session_id: str) -> None:
    """A device that powers off never fires SessionEnd: its sessions stay open on the
    engine until the next start here closes them. Activity age is the only signal that
    separates an orphan from a parallel session still in use — never close a recent one.
    The session file and its cursor stay: an idle session that wakes up keeps its run,
    its ledger and its place in the transcript instead of starting over."""
    if not _SESSIONS_DIR.exists():
        return
    now = time.time()
    for path in _SESSIONS_DIR.glob("*.json"):
        if path.name.endswith(CURSOR_SUFFIX):
            continue
        session_id = path.stem
        if session_id == current_session_id:
            continue
        if now - path.stat().st_mtime < _ORPHAN_IDLE_S:
            continue
        state = _session(session_id)
        run_id = state.get("run_id")
        if run_id is None:
            path.unlink()
            continue
        if state.get("closed_as_orphan"):
            continue
        flush_spool(session_id, run_id)
        if post(f"/machine/sessions/{run_id}/close", {}) is not None:
            state["closed_as_orphan"] = True
            path.write_text(json.dumps(state))


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
    touch_session(claude_session_id)
    event = {"kind": kind, "turn_key": turn_key, "payload": payload}
    run_id = session_run_id(claude_session_id)
    if run_id is None or post(f"/machine/sessions/{run_id}/events", event) is None:
        spool_event(claude_session_id, event)
    elif run_id is not None:
        flush_spool(claude_session_id, run_id)


def cache_renders(renders: list[dict]) -> None:
    _RENDER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # The engine hands over the full set each session: stale files from an earlier key
    # layout or a left workspace must not resurface as extra renders.
    for stale in _RENDER_CACHE_DIR.glob("*.json"):
        stale.unlink()
    for render in renders:
        kind = render.get("kind") or "rubric"
        name = f"{render['scope']}-{render['workspace_id']}-{kind}"
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
