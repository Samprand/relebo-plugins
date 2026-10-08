import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _login
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
        _client.context("PostToolUse", reply.body.get("context") or "")


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: read(payload))
