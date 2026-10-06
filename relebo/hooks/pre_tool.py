import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
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
    answer = _client.post(
        "/memory/sessions/action", _situation.action_of(payload), timeout=_client.GATE_TIMEOUT_S
    )
    if not answer:
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
    payload = _client.read_payload()
    try:
        judge(payload)
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001 - the gate never allows on a failure of its own
        _client.log(HOOK + " " + type(error).__name__ + ": " + str(error)[:300])
        _client.permission("ask", UNREACHED)
