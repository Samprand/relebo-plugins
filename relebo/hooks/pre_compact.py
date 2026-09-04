"""PreCompact: mark that the transcript is about to be compacted — the next
SessionStart(compact) re-injects the renders."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    _client.record_event(
        payload.get("session_id", ""),
        "compaction",
        f"compact-{int(time.time() * 1000)}",
        {"trigger": payload.get("trigger", "")},
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
