"""What a place's files and surroundings say, read by the machine and sent to the memory:
when the engine hands the session a base to check (`check_id` in its answer) or a place no
base is marked by to recognise (`check_id` 0), the README, the manifests, the folders, the
remote, the commits' domains and the repositories beside it are read here and sent, and
what the memory finds comes back as what the agent is told. Nothing is read by the agent
for it."""

from __future__ import annotations

from pathlib import Path

import _client
import _places
import _situation


def send(session_id: str, cwd: str, answer: dict, root: str = "") -> str:
    check_id = answer.get("check_id")
    if check_id is None:
        return ""
    if check_id == 0:
        # the place to recognise: the file's own repository, or the session's folder
        where = root or (str(_situation.root_of(cwd)) if _situation.in_project(cwd) else "")
    else:
        where = _places.about_for(cwd, check_id, _situation.in_project(cwd))
    if not where or not Path(where).is_dir():
        return ""
    place = Path(where)
    text = _situation.about_of(place)
    signals = _situation.signals_of(place)
    if not text and not signals:
        return ""
    reply = _client.post_reply(
        "/memory/sessions/about",
        {
            "origin_id": session_id,
            "foundation_id": check_id or None,
            "folder": place.name,
            "remote": _situation.remote_of(str(place)),
            "text": text,
            "signals": signals,
        },
        timeout=_client.ABOUT_TIMEOUT_S,
    )
    if not reply.ok:
        return ""
    body = reply.body or {}
    if body.get("standing_id") is not None:
        _places.note(body.get("standing_id"), str(place))
    return body.get("context") or ""
