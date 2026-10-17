import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _check
import _client
import _login
import _places
import _situation
import _unread

HOOK = "user_prompt"
LOCAL_PLACE = "On this machine, %s is at %s."
# after a report of what the memory did: how the agent sends the detail of what looked wrong
# to Relebo's maintainers, with this plugin's own script and this session for the trace
REPORT_HEADER = "[Relebo memory · what it did with the person's last message]"
FEEDBACK_HOW = (
    "To send detail to Relebo's maintainers, run: python3 %s --session %s "
    '"<what happened, why it looks wrong, the ids>"'
)


def talk(payload: dict) -> None:
    session_id = str(payload.get("session_id") or "")
    if not _client.identified():
        # a code is waiting: one poll per prompt, and one short line while it waits
        _client.context("UserPromptSubmit", _login.poll(session_id))
        return
    cwd = payload.get("cwd", "")
    root = str(_situation.root_of(cwd))
    place = {
        "folder": _situation.folder_of(cwd),
        "remote": _situation.remote_of(cwd),
        "root": root,
        "in_project": _situation.in_project(cwd),
    }
    # what the engine could not read when it came is read now, before this message, so
    # the person's words are never lost to the memory (2026-10-16: "el 8 descártalo")
    _unread.flush(session_id, place)
    text = payload.get("prompt") or ""
    reply = _client.post_reply(
        "/memory/sessions/prompt", {"origin_id": session_id, "text": text, **place}
    )
    if _login.refused(reply):
        _client.context("UserPromptSubmit", _login.forget(reply, session_id))
        return
    if not reply.ok:
        _unread.keep(session_id, text)
        return
    answer = reply.body
    # a session the words placed, from a folder that is no project, says nothing of where
    # that project is on this machine
    if answer.get("standing_id") is not None and answer.get("standing_id") == answer.get("home_id"):
        _places.note(answer.get("standing_id"), root)
    # a project named from here: where it is on this machine, if a session ever stood there
    local = []
    for named in answer.get("named") or []:
        path = _places.path_of(named.get("foundation_id"))
        if path:
            local.append(LOCAL_PLACE % (named.get("name"), path))
    parts = [answer.get("context") or ""] + local + [_check.send(session_id, cwd, answer)]
    if REPORT_HEADER in (answer.get("context") or ""):
        script = str(Path(__file__).resolve().parent / "feedback.py")
        parts.append(FEEDBACK_HOW % (script, session_id))
    _client.context("UserPromptSubmit", "\n".join(part for part in parts if part))


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: talk(payload))
