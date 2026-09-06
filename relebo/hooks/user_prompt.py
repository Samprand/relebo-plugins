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
    if _client.rubric_context() != _client.RUBRIC_INDEX:
        return
    run_id = _client.session_run_id(claude_session_id)
    if run_id is None:
        return
    recall = _client.post(f"/machine/sessions/{run_id}/recall", {"prompt": prompt})
    if not recall:
        return
    blocks = []
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
