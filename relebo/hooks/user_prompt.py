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
import _review  # noqa: E402

_MAX_PROMPT_CHARS = 4000
_STATUS_PENDING = "pending"
_STATUS_APPROVED = "approved"
_STATUS_CANCELLED = "cancelled"
_DECIDE_TOOL = "mcp__plugin_relebo_relebo__relebo_decide_inbox"


def _call_ended(transcript_path: str, tool_use_id: str) -> bool:
    """A tool_result for the call exists in the transcript: the dialog was answered."""
    if not tool_use_id or not transcript_path or not Path(transcript_path).exists():
        return False
    marker = f'"tool_use_id": "{tool_use_id}"'
    return any(
        marker in line and '"tool_result"' in line
        for line in Path(transcript_path).read_text().splitlines()
    )


def _dismissed(approval: dict, transcript_path: str) -> bool:
    """The gate put this approval in the permission dialog and its call ended while the
    approval is still parked: post_tool never ran, so the dialog was dismissed (Esc or
    decline). A dismissal cancels the entry — it never rejects it."""
    return approval.get("via") == _client.VIA_DIALOG and _call_ended(
        transcript_path, approval.get("tool_use_id") or ""
    )


def _decision_line(approval: dict, status: str) -> str:
    entry_id = approval.get("entry_id")
    if approval.get("tool") == _DECIDE_TOOL:
        if status == _STATUS_CANCELLED:
            return (
                f"- Inbox entry #{entry_id} was CANCELLED: the dialog was dismissed; do not put "
                "it in front of the user again unless they ask."
            )
        return (
            f"- Inbox entry #{entry_id} was {status.upper()} by the user elsewhere; nothing to "
            "relay."
        )
    command = approval.get("command") or ""
    if status == _STATUS_APPROVED:
        return (
            f"- Inbox entry #{entry_id} was APPROVED: run this exact command now, the gate "
            f"will let it through: `{command}`"
        )
    if status == _STATUS_CANCELLED:
        return (
            f"- Inbox entry #{entry_id} was CANCELLED: the dialog was dismissed and `{command}` "
            "did not run; run it only if the user asks for it again."
        )
    return (
        f"- Inbox entry #{entry_id} was {status.upper()}: do not run `{command}` or a variant "
        "of it; tell the user."
    )


def _decided_approvals(claude_session_id: str, transcript_path: str) -> list[str]:
    """Parked actions whose Inbox decision landed since: each becomes an instruction for
    this turn and leaves the pending list. Still-pending ones stay silent, except a
    dismissed dialog, which cancels its entry here."""
    lines: list[str] = []
    for approval in _client.pending_approvals(claude_session_id):
        entry_id = approval.get("entry_id")
        dismissed = _dismissed(approval, transcript_path)
        current = _client.get(f"/machine/sessions/{approval.get('run_id')}/approvals/{entry_id}")
        status = (current or {}).get("status") or _STATUS_PENDING
        if status == _STATUS_PENDING and dismissed:
            answered = _client.answer_approval(entry_id, _client.DECISION_CANCEL)
            status = (answered or {}).get("status") or _STATUS_PENDING
        if status == _STATUS_PENDING:
            if approval.get("tool") == _DECIDE_TOOL and dismissed:
                # The engine took no cancel: decided elsewhere already, or an entry the status
                # route does not serve. The call is over either way.
                _client.clear_pending_approval(claude_session_id, entry_id)
            continue
        _client.clear_pending_approval(claude_session_id, entry_id)
        lines.append(_decision_line(approval, status))
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
    review = _review.delta(payload.get("cwd", ""), prompt)
    guard_findings = _review.guard_findings(review, _client.cached_anchors()) if review else []
    request = {"prompt": prompt}
    if review:
        request.update(
            paths=review["paths"],
            added=review["added"],
            forced=sorted({finding["anchor"] for finding in guard_findings}),
        )
    run_id = _client.session_run_id(claude_session_id)
    recall = (
        _client.post(f"/machine/sessions/{run_id}/recall", request)
        if run_id is not None and _client.rubric_context() == _client.RUBRIC_INDEX
        else None
    ) or {}
    if recall.get("rules"):
        blocks.append("[Relebo rules for this turn]\n" + "\n\n".join(recall["rules"]))
        _client.mark_served(claude_session_id, _client.anchors_of(recall["rules"]))
    if guard_findings:
        blocks.append(
            f"[Relebo review guards — {review['target']}: dispose of each finding in the review]\n"
            + "\n".join(
                f"- [{f['anchor']}] {f['evidence']} Fix: {f['fix']}" for f in guard_findings
            )
        )
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
