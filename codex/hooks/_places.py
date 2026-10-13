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


def about_for(cwd: str, foundation_id, home_id) -> str:
    """Where the base the check is due for lives on this machine: the session's own root
    when that base is the session's home, else where a session once stood under it. A base
    the words brought the session to is never read from the folder it started in."""
    import _situation

    if foundation_id is None:
        return ""
    if home_id is not None and foundation_id == home_id:
        return str(_situation.root_of(cwd))
    return path_of(foundation_id) or ""
