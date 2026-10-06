import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _situation

HOOK = "stop"


def end(payload: dict) -> None:
    if not _client.identified():
        return
    origin_id = str(payload.get("session_id") or "")
    cwd = payload.get("cwd", "")
    root = _situation.root_of(cwd)
    # what this turn touched, as the memory recorded it; what changed in each, as git shows it
    touched = _client.get("/memory/sessions/" + origin_id + "/touched") or {}
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
        },
    )
    if answer and answer.get("send_back"):
        _client.send_back(answer["send_back"])


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: end(payload))
