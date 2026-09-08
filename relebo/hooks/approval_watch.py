"""Waits on one Inbox approval of the action gate and prints a single line when the
human decides. Meant for the agent's Monitor tool after the gate parked an action:

    python3 approval_watch.py <run_id> <entry_id>

Prints `approval <entry_id>: approved|rejected|expired` and exits; silence means the
decision is still pending. Exits non-zero only on bad arguments."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402

_POLL_S = 30
_STATUS_PENDING = "pending"


def main(run_id: int, entry_id: int) -> None:
    while True:
        current = _client.get(f"/machine/sessions/{run_id}/approvals/{entry_id}")
        status = (current or {}).get("status") or _STATUS_PENDING
        if status != _STATUS_PENDING:
            print(f"approval {entry_id}: {status}", flush=True)
            return
        time.sleep(_POLL_S)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: approval_watch.py <run_id> <entry_id>")
    main(int(sys.argv[1]), int(sys.argv[2]))
