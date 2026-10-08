"""Where each project is on this machine: the folder a session stood in under a foundation.
Kept here, never in a memory: twenty people have twenty paths."""

from __future__ import annotations

import json

from _client import MEMORY_DIR, PLACES_FILE


def _load() -> dict:
    try:
        found = json.loads(PLACES_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def note(foundation_id, root: str) -> None:
    if foundation_id is None or not root:
        return
    places = _load()
    if places.get(str(foundation_id)) == root:
        return
    places[str(foundation_id)] = root
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        PLACES_FILE.write_text(json.dumps(places, indent=2, sort_keys=True))
    except OSError:
        pass


def path_of(foundation_id) -> str:
    return _load().get(str(foundation_id), "")
