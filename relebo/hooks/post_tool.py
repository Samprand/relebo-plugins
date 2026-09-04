"""PostToolUse for ExitPlanMode and AskUserQuestion: plan approvals and
question answers are first-class authorization entries in the ledger."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402

_MAX_FIELD_CHARS = 6000


def _trim(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)[:_MAX_FIELD_CHARS]


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    tool = payload.get("tool_name", "")
    _client.record_event(
        payload.get("session_id", ""),
        "authorization",
        f"{tool}-{int(time.time() * 1000)}",
        {
            "tool": tool,
            "input": _trim(payload.get("tool_input") or {}),
            "response": _trim(payload.get("tool_response") or {}),
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
