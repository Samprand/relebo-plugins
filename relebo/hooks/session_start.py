import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _places
import _situation

HOOK = "session_start"


def arrive(payload: dict) -> None:
    if not _client.identified():
        return
    cwd = payload.get("cwd", "")
    answer = _client.post(
        "/memory/sessions/arrive",
        {
            "origin_id": str(payload.get("session_id") or ""),
            "source": payload.get("source") or "startup",
            "folder": _situation.folder_of(cwd),
            "remote": _situation.remote_of(cwd),
        },
    )
    if not answer:
        return
    _places.note(answer.get("standing_id"), str(_situation.root_of(cwd)))
    _client.context("SessionStart", answer.get("context") or "")


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: arrive(payload))
