"""SessionEnd: close the session run on the engine."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    claude_session_id = payload.get("session_id", "")
    run_id = _client.session_run_id(claude_session_id)
    if run_id is None:
        return
    _client.flush_spool(claude_session_id, run_id)
    _client.post(f"/machine/sessions/{run_id}/close", {})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
