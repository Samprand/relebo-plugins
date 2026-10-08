import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _login
import _situation

HOOK = "pre_tool"
OWN_MEMORY_REFUSED = (
    "Do not save memories yourself. What the person teaches is read when the turn ends and "
    "remembered by Relebo's memory. Just answer the person."
)
# the gate fails closed: an action the memory could not judge goes to the person
UNREACHED = (
    "Relebo's memory could not judge this action (the engine did not answer). "
    "Ask the person before doing it."
)
UNREACHED_READ = "engine did not answer; a command that only looks goes through: "


def own_memory(payload: dict) -> bool:
    """Claude Code's own notebook would hide what the memory did not keep."""
    target = str((payload.get("tool_input") or {}).get("file_path") or "")
    return "/.claude/projects/" in target and "/memory/" in target


def judge(payload: dict) -> None:
    if own_memory(payload):
        _client.permission("deny", OWN_MEMORY_REFUSED)
        return
    if not _client.identified():
        return
    # a scratch file is nobody's: nothing of the place is at stake in it
    tool_input = payload.get("tool_input") or {}
    if _situation.scratch(str(tool_input.get("file_path") or "")):
        return
    if payload.get("tool_name") == "Bash" and _situation.scratch_command(str(tool_input.get("command") or "")):
        return
    reply = _client.post_reply(
        "/memory/sessions/action", _situation.action_of(payload), timeout=_client.GATE_TIMEOUT_S
    )
    if _login.refused(reply):
        # the token is gone: the person is told why, once, and this action is theirs to allow
        _client.permission("ask", _login.forget(reply, str(payload.get("session_id") or "")))
        return
    answer = reply.body if reply.ok else None
    if not answer:
        # the gate fails closed, except for a command that only looks: nothing of the place
        # is at stake in it, and the person is not asked about every ls
        command = str(tool_input.get("command") or "")
        if payload.get("tool_name") == "Bash" and _situation.read_only(command):
            _client.log(HOOK + " " + UNREACHED_READ + command[:120])
            return
        _client.permission("ask", UNREACHED)
        return
    decision = answer.get("decision")
    if decision == "hold":
        _client.permission("deny", answer.get("reason") or "")
    elif decision == "ask":
        _client.permission("ask", answer.get("reason") or "", answer.get("context") or "")
    else:
        _client.context("PreToolUse", answer.get("context") or "")


if __name__ == "__main__":
    try:
        judge(_client.read_payload())
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001 - the gate never allows on a failure of its own
        _client.log(HOOK + " " + type(error).__name__ + ": " + str(error)[:300])
        _client.permission("ask", UNREACHED)
