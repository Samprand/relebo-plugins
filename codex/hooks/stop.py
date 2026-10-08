import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _login
import _situation

HOOK = "stop"


def end(payload: dict) -> None:
    if not _client.identified():
        return
    origin_id = str(payload.get("session_id") or "")
    cwd = payload.get("cwd", "")
    root = _situation.root_of(cwd)
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
    answer = _client.post(
        "/memory/sessions/end",
        {
            "origin_id": origin_id,
            "answer": payload.get("last_assistant_message") or "",
            "changed": changed,
            "root": str(root),
            "folder": root.name,
            "remote": _situation.remote_of(cwd),
        },
    )
    if answer and answer.get("send_back"):
        _client.send_back(answer["send_back"])


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: end(payload))
