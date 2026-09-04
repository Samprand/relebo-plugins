"""UserPromptSubmit: every user prompt joins the session ledger — mid-turn
instructions and authorizations included, so the gate never loses them."""

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
    _client.record_event(
        payload.get("session_id", ""),
        "user_prompt",
        f"prompt-{int(time.time() * 1000)}",
        {"prompt": prompt},
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
