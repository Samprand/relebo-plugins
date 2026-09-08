"""PostToolUse for ExitPlanMode and AskUserQuestion: plan approvals and question
answers are first-class authorization entries in the ledger. For Bash: a command that
ran after the gate asked through the permission dialog means the user approved it there;
the decision is relayed to its Inbox entry, which writes the ledger.

Only what the user actually chose is recorded. The options offered never enter the
ledger: a judge reading them would take a menu for an approval."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402

_MAX_FIELD_CHARS = 6000
_ASK_USER_QUESTION = "AskUserQuestion"
_BASH = "Bash"
_VIA_DIALOG = "dialog"
_DECISION_APPROVE = "approve"


def _trim(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)[:_MAX_FIELD_CHARS]


def _authorization(tool: str, tool_input: dict, tool_response: object) -> dict | None:
    if tool != _ASK_USER_QUESTION:
        return {"tool": tool, "input": _trim(tool_input), "response": _trim(tool_response)}
    response = tool_response if isinstance(tool_response, dict) else {}
    answers = response.get("answers") or {}
    if not answers:
        # Dismissed or interrupted: nothing was approved.
        return None
    return {
        "tool": tool,
        "answers": _trim(answers),
        "annotations": _trim(response.get("annotations") or {}),
    }


def _relay_dialog_approval(payload: dict) -> None:
    """The command ran, so the dialog the gate opened was approved: the Inbox entry learns it."""
    session_id = payload.get("session_id", "")
    tool_use_id = payload.get("tool_use_id") or ""
    command = (payload.get("tool_input") or {}).get("command") or ""
    for approval in _client.pending_approvals(session_id):
        if approval.get("via") != _VIA_DIALOG:
            continue
        same_call = tool_use_id and approval.get("tool_use_id") == tool_use_id
        if not same_call and approval.get("command") != command:
            continue
        _client.answer_approval(approval["entry_id"], _DECISION_APPROVE)
        _client.clear_pending_approval(session_id, approval["entry_id"])


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    tool = payload.get("tool_name", "")
    if tool == _BASH:
        _relay_dialog_approval(payload)
        return
    entry = _authorization(tool, payload.get("tool_input") or {}, payload.get("tool_response"))
    if entry is None:
        return
    _client.record_event(
        payload.get("session_id", ""),
        "authorization",
        f"{tool}-{int(time.time() * 1000)}",
        entry,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
