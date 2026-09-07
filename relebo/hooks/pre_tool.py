"""PreToolUse: the machine-scope supervisor's gate BEFORE an action runs.

- Shell commands: each subcommand is classified by effect. Destructive ones are denied
  here, deterministically. Remote (push, deploy, release, secrets, production database)
  and shared-repo (commit, merge) effects go to the engine's action gate, which judges
  them against the session's authorization ledger and the applicable rules: allow runs,
  deny stops, ask parks the action as an Inbox approval and stops until the human
  answers there (an approval lets the rerun through, a rejection denies it and its
  variants). Without the engine the action asks the terminal: never a silent pass.
- File writes: Claude Code's per-repo auto-memory is where an agent without a memory
  tool parks what the user just said. Relebo already captures it from the session, and
  the rubric forbids that store — so the write is denied at the tool, not after the turn.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402
import _git  # noqa: E402
import _guards  # noqa: E402

_REPO_MEMORY_RE = re.compile(r"/\.claude/projects/[^/]+/memory(/|$)")
_COMMIT_MESSAGE_RE = re.compile(r"""-m\s+(?:"([^"]*)"|'([^']*)'|(\S+))""")
_ACTION_GATE_TIMEOUT_S = 25
_MAX_COMMAND_CHARS = 2000
_MAX_CHANGES_CHARS = 4000
_DECISION_ASK = "ask"
_DECISION_DENY = "deny"


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
        # The human decides in the Inbox, not in a terminal dialog: the action stops here
        # and runs only once the ledger holds the approval (rerun the command after it).
        entry = verdict.get("inbox_entry_id")
        where = f"Inbox entry #{entry}" if entry else "your Inbox"
        _decide(
            _DECISION_DENY,
            f"Relebo supervisor: {detail} Awaiting the user's decision in {where}. Stop this "
            "line of work, tell the user what is pending, and run the command again only "
            "after they approve it there.",
        )


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


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    tool_input = payload.get("tool_input") or {}
    if payload.get("tool_name") == "Bash":
        _gate_command(payload, tool_input)
        return
    _guard_memory_write(tool_input)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
