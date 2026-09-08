"""UserPromptSubmit: every user prompt joins the session ledger — mid-turn
instructions and authorizations included, so the gate never loses them. With the
rubric in index mode, the prompt also pulls the rules and project facts this turn
calls for."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402

_MAX_PROMPT_CHARS = 4000
_STATUS_PENDING = "pending"
_STATUS_APPROVED = "approved"
_VIA_DIALOG = "dialog"
_DECISION_REJECT = "reject"


def _call_ended(transcript_path: str, tool_use_id: str) -> bool:
    """A tool_result for the call exists in the transcript: the dialog was answered."""
    if not tool_use_id or not transcript_path or not Path(transcript_path).exists():
        return False
    marker = f'"tool_use_id": "{tool_use_id}"'
    return any(
        marker in line and '"tool_result"' in line
        for line in Path(transcript_path).read_text().splitlines()
    )


def _decided_approvals(claude_session_id: str, transcript_path: str) -> list[str]:
    """Parked actions whose Inbox decision landed since: each becomes an instruction for
    this turn and leaves the pending list. Still-pending ones stay silent. An approval the
    gate put in the permission dialog and that is still pending once its call ended was
    declined there: post_tool never ran, so the decline is relayed here."""
    lines: list[str] = []
    for approval in _client.pending_approvals(claude_session_id):
        current = _client.get(
            f"/machine/sessions/{approval.get('run_id')}/approvals/{approval.get('entry_id')}"
        )
        status = (current or {}).get("status") or _STATUS_PENDING
        if (
            status == _STATUS_PENDING
            and approval.get("via") == _VIA_DIALOG
            and _call_ended(transcript_path, approval.get("tool_use_id") or "")
        ):
            answered = _client.answer_approval(approval.get("entry_id"), _DECISION_REJECT)
            status = (answered or {}).get("status") or _STATUS_PENDING
        if status == _STATUS_PENDING:
            continue
        _client.clear_pending_approval(claude_session_id, approval.get("entry_id"))
        command = approval.get("command") or ""
        if status == _STATUS_APPROVED:
            lines.append(
                f"- Inbox entry #{approval.get('entry_id')} was APPROVED: run this exact command "
                f"now, the gate will let it through: `{command}`"
            )
        else:
            lines.append(
                f"- Inbox entry #{approval.get('entry_id')} was {status.upper()}: do not run "
                f"`{command}` or a variant of it; tell the user."
            )
    return lines


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    prompt = (payload.get("prompt") or "")[:_MAX_PROMPT_CHARS]
    if not prompt.strip():
        return
    claude_session_id = payload.get("session_id", "")
    _client.ensure_session(claude_session_id, payload.get("cwd", ""))
    _client.record_event(
        claude_session_id,
        "user_prompt",
        f"prompt-{int(time.time() * 1000)}",
        {"prompt": prompt},
    )
    blocks = []
    decided = _decided_approvals(claude_session_id, payload.get("transcript_path", ""))
    if decided:
        blocks.append("[Relebo action gate — decisions since your last prompt]\n" + "\n".join(decided))
    run_id = _client.session_run_id(claude_session_id)
    recall = (
        _client.post(f"/machine/sessions/{run_id}/recall", {"prompt": prompt})
        if run_id is not None and _client.rubric_context() == _client.RUBRIC_INDEX
        else None
    ) or {}
    if recall.get("rules"):
        blocks.append("[Relebo rules for this turn]\n" + "\n\n".join(recall["rules"]))
    if recall.get("facts"):
        blocks.append("[Relebo project facts for this turn]\n" + "\n".join(f"- {f}" for f in recall["facts"]))
    if blocks:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": "\n\n".join(blocks),
                    }
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
