import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _situation

HOOK = "post_tool"


def read(payload: dict) -> None:
    if not _client.identified():
        return
    action = _situation.action_of(payload)
    action.pop("written", None)
    answer = _client.post("/memory/sessions/result", action)
    if answer:
        _client.context("PostToolUse", answer.get("context") or "")


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: read(payload))
