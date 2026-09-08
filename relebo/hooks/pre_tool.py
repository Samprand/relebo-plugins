"""PreToolUse: the machine-scope supervisor's gate BEFORE an action runs.

- Shell commands: each subcommand is classified by effect. Destructive ones are denied
  here, deterministically. Remote (push, deploy, release, secrets, production database)
  and shared-repo (commit, merge) effects go to the engine's action gate, which judges
  them against the session's authorization ledger and the applicable rules: allow runs,
  deny stops, ask opens an Inbox approval and puts it in front of the human: in the
  permission modes where Claude Code always prompts, as the native permission dialog
  (approving runs the command and the post hook records the decision; declining leaves
  it undone); in the other modes the action parks until the human answers in the Inbox.
  Without the engine the action asks the terminal: never a silent pass.
- The Relebo decide tool: always behind the native dialog, so adopting a rubric proposal
  or answering an approval is the user's click, never the agent's call.
- File writes: Claude Code's per-repo auto-memory is where an agent without a memory
  tool parks what the user just said. Relebo already captures it from the session, and
  the rubric forbids that store — so the write is denied at the tool, not after the turn.
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402
import _git  # noqa: E402
import _guards  # noqa: E402

_REPO_MEMORY_RE = re.compile(r"/\.claude/projects/[^/]+/memory(/|$)")
_COMMIT_MESSAGE_RE = re.compile(r"""-m\s+(?:"([^"]*)"|'([^']*)'|(\S+))""")
_ACTION_GATE_TIMEOUT_S = 25
# How long the hook waits for the human's Inbox decision before parking the action.
# Below the hook timeout in hooks.json so a slow answer degrades to "pending", never to
# a killed hook.
_APPROVAL_WAIT_S = 540
_APPROVAL_POLL_S = 5
_STATUS_APPROVED = "approved"
_STATUS_PENDING = "pending"
_MAX_COMMAND_CHARS = 2000
_MAX_CHANGES_CHARS = 4000
_DECISION_ASK = "ask"
_DECISION_DENY = "deny"
# Permission modes where Claude Code shows the dialog for every unlisted tool call, so an
# "ask" from this hook is a real question to the human. Elsewhere (auto, bypass, plan) the
# prompt may never appear, and the Inbox stays the only path.
_DIALOG_MODES = ("default", "acceptEdits")
_VIA_DIALOG = "dialog"
_DECIDE_TOOL = "mcp__plugin_relebo_relebo__relebo_decide_inbox"
_DECISIONS = ("approve", "reject")


def _decide(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _pending_changes(cwd: str, command: str) -> dict:
    """What a commit would carry: the tree state now (a `git add` in the same line has
    not run yet, so staged alone would understate it) and the message on the line."""
    message = ""
    match = _COMMIT_MESSAGE_RE.search(command)
    if match:
        message = next(group for group in match.groups() if group is not None)
    return {
        "status": _git.run(cwd, "status", "--porcelain")[:_MAX_CHANGES_CHARS],
        "diff_stat": _git.run(cwd, "diff", "HEAD", "--stat")[:_MAX_CHANGES_CHARS],
        "message": message,
    }


def _gate_command(payload: dict, tool_input: dict) -> None:
    command = tool_input.get("command") or ""
    effects = _guards.command_effects(command)
    if not effects:
        return
    destructive = [item["command"] for item in effects if item["effect"] == _guards.EFFECT_DESTRUCTIVE]
    if destructive:
        _decide(
            _DECISION_DENY,
            "Relebo supervisor: destructive action denied — "
            + "; ".join(destructive)
            + ". Irreversible commands never run from a session; the user runs them by hand.",
        )
        return
    bypass = [item["command"] for item in effects if item["effect"] == _guards.EFFECT_KNOWLEDGE_BYPASS]
    if bypass:
        _decide(
            _DECISION_DENY,
            "Relebo supervisor: knowledge bypass denied — "
            + "; ".join(bypass)
            + ". Rules and approvals reach Relebo only through the Inbox: end the turn with a "
            "Rubric addition block, or ask the user to decide there.",
        )
        return
    session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", "")
    action = {
        "command": command[:_MAX_COMMAND_CHARS],
        "effects": effects,
        "cwd": cwd,
        "description": (tool_input.get("description") or "")[:_MAX_COMMAND_CHARS],
        "changes": {},
    }
    if any(item["command"].startswith("git commit") for item in effects):
        action["changes"] = _pending_changes(cwd, command)
    summary = "; ".join(item["command"] for item in effects)
    run_id = _client.ensure_session(session_id, cwd)
    verdict = (
        _client.post(f"/machine/sessions/{run_id}/gate-action", action, timeout=_ACTION_GATE_TIMEOUT_S)
        if run_id is not None
        else None
    )
    if verdict is None:
        _decide(
            _DECISION_ASK,
            f"Relebo supervisor unreachable — confirm this remote action yourself: {summary}",
        )
        return
    mode = verdict.get("mode") or _client.session_gate_mode(session_id)
    if mode != _client.ENFORCE:
        # Shadow: judged and audited, never in the way.
        return
    decision = verdict.get("decision")
    detail = verdict.get("summary") or summary
    reason = verdict.get("reason") or ""
    if decision == _DECISION_DENY:
        _decide(_DECISION_DENY, f"Relebo supervisor: {detail}" + (f" — {reason}" if reason else ""))
    elif decision == _DECISION_ASK:
        entry = verdict.get("inbox_entry_id")
        if entry and payload.get("permission_mode") in _DIALOG_MODES:
            # The native permission dialog is the form: the user approves or declines by
            # hand. Approving runs the command and post_tool relays the decision to the
            # Inbox entry; declining leaves the entry pending until the next prompt.
            _client.record_pending_approval(
                session_id,
                {
                    "entry_id": entry,
                    "run_id": run_id,
                    "command": action["command"],
                    "summary": detail,
                    "tool_use_id": payload.get("tool_use_id") or "",
                    "via": _VIA_DIALOG,
                },
            )
            _decide(
                _DECISION_ASK,
                f"Relebo supervisor: {detail} Inbox entry #{entry}. Approving here runs the "
                "command and records your decision; declining leaves it undone.",
            )
            return
        # No dialog in this permission mode: the human decides in the Inbox. The hook waits
        # for that decision: approved runs the command right now, rejected or lapsed denies
        # it, and only a long silence parks it for a later rerun the ledger will let through.
        outcome = _await_decision(run_id, entry) if entry else _STATUS_PENDING
        if outcome == _STATUS_APPROVED:
            return
        where = f"Inbox entry #{entry}" if entry else "your Inbox"
        if outcome == _STATUS_PENDING:
            if entry:
                _client.record_pending_approval(
                    session_id,
                    {"entry_id": entry, "run_id": run_id, "command": action["command"], "summary": detail},
                )
            watcher = Path(__file__).resolve().parent / "approval_watch.py"
            _decide(
                _DECISION_DENY,
                f"Relebo supervisor: {detail} Awaiting the user's decision in {where}. Do not "
                "run this command again now. To resume without the user, arm the Monitor tool "
                f"with `python3 {watcher} {run_id} {entry}` (persistent): it prints one line "
                "when the decision lands; on `approved` run the exact same command, on "
                "`rejected` or `expired` stop and tell the user. Then continue with other work.",
            )
            return
        _decide(
            _DECISION_DENY,
            f"Relebo supervisor: {detail} The user marked {where} as {outcome}; do not retry "
            "this action or a variant of it.",
        )


def _await_decision(run_id: int, entry_id: int) -> str:
    """Polls the approval until the human answers or the wait budget ends."""
    deadline = time.monotonic() + _APPROVAL_WAIT_S
    while time.monotonic() < deadline:
        current = _client.get(f"/machine/sessions/{run_id}/approvals/{entry_id}")
        status = (current or {}).get("status") or _STATUS_PENDING
        if status != _STATUS_PENDING:
            return status
        time.sleep(_APPROVAL_POLL_S)
    return _STATUS_PENDING


def _guard_memory_write(tool_input: dict) -> None:
    file_path = tool_input.get("file_path") or ""
    if not _REPO_MEMORY_RE.search(file_path):
        return
    _decide(
        _DECISION_DENY,
        f"{file_path} is Claude Code's per-repo memory, which this project does "
        "not use: Relebo captures what the user states from the session by "
        "itself. Do not persist it by hand; when the user asks to keep something "
        "for the team, call relebo_save_knowledge.",
    )


def _gate_decide(payload: dict, tool_input: dict) -> None:
    """The decide tool is the agent's way to put a proposal or approval in front of the
    user; the answer is the user's click in the dialog, so without a dialog it does not run."""
    entry_id = tool_input.get("entry_id")
    verb = str(tool_input.get("decision") or "")
    if verb not in _DECISIONS or not entry_id:
        _decide(_DECISION_DENY, "Relebo: relebo_decide_inbox needs entry_id and decision approve|reject.")
        return
    if payload.get("permission_mode") not in _DIALOG_MODES:
        _decide(
            _DECISION_DENY,
            f"Relebo: this permission mode shows no dialog, so Inbox entry #{entry_id} is "
            "decided by the user in the Inbox, not here.",
        )
        return
    _decide(
        _DECISION_ASK,
        f"Relebo: you are about to {verb.upper()} Inbox entry #{entry_id}. Only you decide: "
        "approving here is the decision itself.",
    )


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    tool_input = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    if tool == "Bash":
        _gate_command(payload, tool_input)
        return
    if tool == _DECIDE_TOOL:
        _gate_decide(payload, tool_input)
        return
    _guard_memory_write(tool_input)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
