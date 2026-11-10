import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _held
import _login
import _situation
import _unread

HOOK = "stop"
EVENT = _client.STOP_EVENT


def end(payload: dict) -> None:
    if not _client.identified():
        return
    origin_id = str(payload.get("session_id") or "")
    cwd = payload.get("cwd", "")
    root = _situation.root_of(cwd)
    # a hold the turn did not answer does not outlive it
    _held.forget(origin_id)
    # a prompt of this turn the engine could not read when it came is read before the turn
    # closes, so what the person said this turn is what the turn is read with
    _unread.flush(
        origin_id,
        {
            "folder": _situation.folder_of(cwd),
            "remote": _situation.remote_of(cwd),
            "root": str(root),
            "in_project": _situation.in_project(cwd),
        },
    )
    # what this turn touched, as the memory recorded it; what changed in each, as git shows it
    first = _client.get_reply("/memory/sessions/" + origin_id + "/touched")
    if _login.refused(first):
        # the turn is over; the cause is logged, and the next prompt shows the new code
        _client.log(HOOK + " " + _login.forget(first, origin_id))
        return
    touched = first.body if first.ok else {}
    changed = {}
    for path in touched.get("touched") or []:
        lines = _situation.changed_lines(root, path)
        if lines:
            changed[path] = lines
    reply = _client.post_reply(
        "/memory/sessions/end",
        {
            "origin_id": origin_id,
            "answer": payload.get("last_assistant_message") or "",
            "changed": changed,
            "root": str(root),
            "folder": root.name,
            "remote": _situation.remote_of(cwd),
        },
        timeout=_client.END_TIMEOUT_S,
    )
    if _login.refused(reply):
        _client.log(HOOK + " " + _login.forget(reply, origin_id))
        return
    if not reply.ok:
        # the turn is over and the agent will not read a note: the person does
        _client.unreached(EVENT, HOOK, "/memory/sessions/end " + str(reply.status))
        return
    if reply.body.get("send_back"):
        _client.send_back(reply.body["send_back"])


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: end(payload), EVENT)
