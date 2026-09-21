"""PostToolUse for ExitPlanMode and AskUserQuestion: plan approvals and question
answers are first-class authorization entries in the ledger. For Bash: a command that
ran after the gate asked through the permission dialog means the user approved it there;
the decision is relayed to its Inbox entry, which writes the ledger. For the Relebo
decide tool: it ran, so its dialog was approved and the tool answered the entry itself; the
parked call is forgotten, or the next prompt would read it as dismissed.

For Write/Edit/MultiEdit: the rules the written path and content call for come back as
additional context right away — the earliest channel Claude Code offers, since PreToolUse
carries no context — each rule once per session, so the agent corrects in the same turn
instead of the Stop gate correcting after it.

Only what the user actually chose is recorded. The options offered never enter the
ledger: a judge reading them would take a menu for an approval."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402
import _guards  # noqa: E402

_MAX_FIELD_CHARS = 6000
_RECALL_TIMEOUT_S = 8
_RECALL_KIND_WRITE = "write"
_ASK_USER_QUESTION = "AskUserQuestion"
_BASH = "Bash"
_DECIDE_TOOL = "mcp__plugin_relebo_relebo__relebo_decide_inbox"
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


def _forget_decided_call(payload: dict) -> None:
    """The decide tool ran: the user allowed it and it answered the entry, so nothing is
    left to relay for that call."""
    session_id = payload.get("session_id", "")
    tool_use_id = payload.get("tool_use_id") or ""
    entry_id = (payload.get("tool_input") or {}).get("entry_id")
    for approval in _client.pending_approvals(session_id):
        same_call = tool_use_id and approval.get("tool_use_id") == tool_use_id
        if same_call or approval.get("entry_id") == entry_id:
            _client.clear_pending_approval(session_id, approval["entry_id"])


def _written(tool: str, tool_input: dict) -> str:
    if tool == "Write":
        return tool_input.get("content") or ""
    if tool == "MultiEdit":
        return "\n".join((e or {}).get("new_string") or "" for e in tool_input.get("edits") or [])
    return tool_input.get("new_string") or tool_input.get("new_source") or ""


def _fresh(rendered: list[str], served: set[str]) -> list[str]:
    return [rule for rule in rendered if not (_client.anchors_of([rule]) & served)]


def _rules_for_write(payload: dict) -> str | None:
    session_id = payload.get("session_id", "")
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path or _guards.EXEMPT_PATH_RE.search(path):
        return None
    run_id = _client.session_run_id(session_id)
    if run_id is None or _client.rubric_context() != _client.RUBRIC_INDEX:
        return None
    recall = (
        _client.post(
            f"/machine/sessions/{run_id}/recall",
            {
                "prompt": "",
                "paths": [path],
                "added": {path: _written(tool, tool_input)},
                "kind": _RECALL_KIND_WRITE,
            },
            timeout=_RECALL_TIMEOUT_S,
        )
        or {}
    )
    fresh = _fresh(recall.get("rules") or [], _client.served_anchors(session_id))
    if not fresh:
        return None
    _client.mark_served(session_id, _client.anchors_of(fresh))
    return f"[Relebo rules for what you just wrote — {path}]\n" + "\n\n".join(fresh)


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    tool = payload.get("tool_name", "")
    if tool == _BASH:
        _relay_dialog_approval(payload)
        return
    if tool == _DECIDE_TOOL:
        _forget_decided_call(payload)
        return
    if tool in _guards.EDIT_TOOLS:
        context = _rules_for_write(payload)
        if context:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": context,
                        }
                    }
                )
            )
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
