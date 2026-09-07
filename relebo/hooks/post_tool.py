"""PostToolUse for ExitPlanMode and AskUserQuestion: plan approvals and question
answers are first-class authorization entries in the ledger.

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


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    tool = payload.get("tool_name", "")
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
