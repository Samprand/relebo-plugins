"""SessionEnd: cancel the dialogs the session left unanswered, then close its run on
the engine."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402

_CLOSE_TIMEOUT_S = 280


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    claude_session_id = payload.get("session_id", "")
    run_id = _client.session_run_id(claude_session_id)
    if run_id is None:
        return
    _client.cancel_dismissed_dialogs(claude_session_id)
    _client.flush_spool(claude_session_id, run_id)
    # The close digests the session on the machine's engine: capture, reconcile and the
    # rubric proposals its blocks earned, each one CLI run.
    _client.post(f"/machine/sessions/{run_id}/close", {}, timeout=_CLOSE_TIMEOUT_S)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
