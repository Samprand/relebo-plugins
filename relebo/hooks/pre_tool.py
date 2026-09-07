"""PreToolUse for file writes: Claude Code's per-repo auto-memory is where an agent
without a memory tool parks what the user just said. Relebo already captures it from
the session, and the rubric forbids that store — so the write is denied at the tool,
not after the turn."""

import json
import re
import sys

_REPO_MEMORY_RE = re.compile(r"/\.claude/projects/[^/]+/memory(/|$)")


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not _REPO_MEMORY_RE.search(file_path):
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{file_path} is Claude Code's per-repo memory, which this project does "
                        "not use: Relebo captures what the user states from the session by "
                        "itself. Do not persist it by hand; when the user asks to keep something "
                        "for the team, call relebo_save_knowledge."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
