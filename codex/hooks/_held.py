"""The last action the gate held in each session, kept on this device so the next action can
be told apart from a repeat of it (Part 8, second change): the same action sent again
unchanged is the signal `overridden` of the memory's learning, and nobody else can see it.
Stdlib only, as every hook module."""

from __future__ import annotations

import hashlib
import json

import _client

HELD_FILE = _client.MEMORY_DIR / "held.json"


def signature(action: dict) -> str:
    """What makes two actions the same: the tool, the file or the command, and the lines it
    would write. A character changed is another action."""
    facets = {
        "tool": action.get("tool") or "",
        "path": action.get("path") or "",
        "command": action.get("command") or "",
        "written": action.get("written") or [],
    }
    return hashlib.sha256(json.dumps(facets, sort_keys=True).encode("utf-8")).hexdigest()


def repeats(session_id: str, action: dict) -> bool:
    kept = _client.read_json(HELD_FILE).get(session_id)
    return bool(kept) and kept == signature(action)


def note(session_id: str, action: dict) -> None:
    """The action just held, in place of the one before: the last held, nothing more."""
    kept = _client.read_json(HELD_FILE)
    kept[session_id] = signature(action)
    # a device keeps the last held action of its last few sessions, not a history
    if len(kept) > 20:
        for old in list(kept)[: len(kept) - 20]:
            kept.pop(old, None)
    _client.write_json(HELD_FILE, kept)


def forget(session_id: str) -> None:
    kept = _client.read_json(HELD_FILE)
    if session_id in kept:
        kept.pop(session_id)
        _client.write_json(HELD_FILE, kept)
