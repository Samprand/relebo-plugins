import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _login
import _places
import _situation

HOOK = "session_start"


def arrive(payload: dict) -> None:
    session_id = str(payload.get("session_id") or "")
    if not _client.identified():
        # no token on this device: a code to approve on the web, shown where the person reads
        _client.context("SessionStart", _login.begin_at_session_start(session_id=session_id))
        return
    cwd = payload.get("cwd", "")
    reply = _client.post_reply(
        "/memory/sessions/arrive",
        {
            "origin_id": session_id,
            "source": payload.get("source") or "startup",
            "folder": _situation.folder_of(cwd),
            "remote": _situation.remote_of(cwd),
            "in_project": _situation.in_project(cwd),
        },
    )
    if _login.refused(reply):
        _client.context("SessionStart", _login.forget(reply, session_id))
        return
    if not reply.ok:
        return
    answer = reply.body
    _places.note(answer.get("standing_id"), str(_situation.root_of(cwd)))
    _client.context("SessionStart", answer.get("context") or "")


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: arrive(payload))
