import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _check
import _client
import _login
import _places
import _situation

HOOK = "post_tool"


def read(payload: dict) -> None:
    if not _client.identified():
        return
    action = _situation.action_of(payload)
    action.pop("written", None)
    reply = _client.post_reply("/memory/sessions/result", action)
    if _login.refused(reply):
        _client.context("PostToolUse", _login.forget(reply, str(payload.get("session_id") or "")))
        return
    if reply.ok:
        # the file's repository is where the session now stands: that is where the project is
        if action.get("path") is not None and action.get("remote"):
            _places.note(reply.body.get("standing_id"), action["root"])
        # a repository no base is marked by: its files are read here and sent, to recognise it
        told = _check.send(str(payload.get("session_id") or ""), payload.get("cwd", ""), reply.body, action.get("root", ""))
        parts = [reply.body.get("context") or "", told]
        _client.context("PostToolUse", "\n".join(part for part in parts if part))


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: read(payload))
