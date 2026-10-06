import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _places
import _situation

HOOK = "user_prompt"
LOCAL_PLACE = "On this machine, %s is at %s."


def talk(payload: dict) -> None:
    if not _client.identified():
        return
    cwd = payload.get("cwd", "")
    root = str(_situation.root_of(cwd))
    answer = _client.post(
        "/memory/sessions/prompt",
        {
            "origin_id": str(payload.get("session_id") or ""),
            "text": payload.get("prompt") or "",
            "folder": _situation.folder_of(cwd),
            "remote": _situation.remote_of(cwd),
            "root": root,
        },
    )
    if not answer:
        return
    _places.note(answer.get("standing_id"), root)
    # a project named from here: where it is on this machine, if a session ever stood there
    local = []
    for named in answer.get("named") or []:
        path = _places.path_of(named.get("foundation_id"))
        if path:
            local.append(LOCAL_PLACE % (named.get("name"), path))
    parts = [answer.get("context") or ""] + local
    _client.context("UserPromptSubmit", "\n".join(part for part in parts if part))


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: talk(payload))
