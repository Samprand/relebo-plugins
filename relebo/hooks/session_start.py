import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _check
import _client

# what the agent can ask the memory by hand, told once at arrival (2026-11-17)
SEARCH_HOW = (
    "To look through the memory by words before saying what it holds, run: python3 %s "
    '--session %s "<words>"'
)
FEEDBACK_HOW = (
    "To send detail to Relebo's maintainers when the memory did something wrong, run: "
    'python3 %s --session %s "<what happened, why it looks wrong, the ids>"'
)
WORK_HOW = (
    "The person's work in Relebo (their workspaces and teams, the workflows of each, starting "
    "one, a one-off plan, following a run) is reached with: python3 %s  — alone it lists the "
    "tools and what each takes; with a tool's name and its input as JSON it calls one."
)
import _login
import _places
import _situation

HOOK = "session_start"
EVENT = "SessionStart"


def arrive(payload: dict) -> None:
    session_id = str(payload.get("session_id") or "")
    if not _client.identified():
        # no token on this device: a code to approve on the web, shown where the person reads
        _client.context("SessionStart", _login.begin_at_session_start(session_id=session_id))
        return
    cwd = payload.get("cwd", "")
    _client.note_session(cwd, session_id)
    reply = _client.post_reply(
        "/memory/sessions/arrive",
        {
            "origin_id": session_id,
            "source": payload.get("source") or "startup",
            "folder": _situation.folder_of(cwd),
            "remote": _situation.remote_of(cwd),
            "in_project": _situation.in_project(cwd),
            "locale": _situation.locale_of(),
            "time_zone": _situation.time_zone_of(),
        },
    )
    if _login.refused(reply):
        _client.context("SessionStart", _login.forget(reply, session_id))
        return
    if not reply.ok:
        _client.unreached(EVENT, HOOK, "/memory/sessions/arrive " + str(reply.status))
        return
    answer = reply.body
    # where that project is on this machine: only when the base is the session's own folder
    if answer.get("standing_id") is not None and answer.get("standing_id") == answer.get("home_id"):
        _places.note(answer.get("standing_id"), str(_situation.root_of(cwd)))
    here = Path(__file__).resolve().parent
    parts = [answer.get("context") or "", _check.send(session_id, cwd, answer)]
    if _client.CLIENT_ID == "codex":
        # Codex has no tools of the plugin's: the scripts, told once at arrival
        parts += [
            SEARCH_HOW % (str(here / "search.py"), session_id),
            FEEDBACK_HOW % (str(here / "feedback.py"), session_id),
            WORK_HOW % str(here / "work.py"),
        ]
    _client.context("SessionStart", "\n".join(part for part in parts if part))


if __name__ == "__main__":
    payload = _client.read_payload()
    _client.run(HOOK, lambda: arrive(payload), EVENT)
