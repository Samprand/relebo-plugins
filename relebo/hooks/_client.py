"""What every hook of the Relebo plugin shares: who this machine is to the engine, how it
posts, and where it keeps what is only this machine's. Stdlib only: hooks run on the system
python3, which may be 3.9, so annotations stay postponed."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

RELEBO_DIR = Path.home() / ".relebo"
MACHINE_FILE = RELEBO_DIR / "machine.json"
MEMORY_DIR = RELEBO_DIR / "memory"
LOG_FILE = MEMORY_DIR / "hooks.log"
PLACES_FILE = MEMORY_DIR / "places.json"
DEFAULT_ENGINE = "http://127.0.0.1:8100"
TIMEOUT_S = 60.0
# a hook that gates an action waits less: the person is waiting on the other side
GATE_TIMEOUT_S = 25.0


def _machine() -> dict:
    try:
        return json.loads(MACHINE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def engine_url() -> str:
    return (
        os.environ.get("CLAUDE_PLUGIN_OPTION_ENGINE_URL")
        or os.environ.get("RELEBO_ENGINE_URL")
        or _machine().get("engine_url")
        or DEFAULT_ENGINE
    ).rstrip("/")


def headers() -> dict:
    """The person this machine acts as: a session token when one is set, else the machine's
    own key, which the engine resolves to its owner. Nothing of the database travels here."""
    found = {"Content-Type": "application/json"}
    token = os.environ.get("CLAUDE_PLUGIN_OPTION_TOKEN") or os.environ.get("RELEBO_TOKEN")
    if token:
        found["Authorization"] = "Bearer " + token
        return found
    key = os.environ.get("RELEBO_MACHINE_KEY") or _machine().get("fingerprint", "")
    if key:
        found["X-Machine-Key"] = key
    return found


def identified() -> bool:
    sent = headers()
    return "Authorization" in sent or "X-Machine-Key" in sent


def _call(request: urllib.request.Request, timeout: float, path: str) -> dict | None:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as error:
        log("call " + path + " failed: " + str(error)[:300])
        return None


def post(path: str, body: dict, timeout: float = TIMEOUT_S) -> dict | None:
    """POST to the engine; None on any failure. Hooks never raise."""
    data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    request = urllib.request.Request(
        engine_url() + path, data=data, headers=headers(), method="POST"
    )
    return _call(request, timeout, path)


def get(path: str, timeout: float = TIMEOUT_S) -> dict | None:
    request = urllib.request.Request(engine_url() + path, headers=headers(), method="GET")
    return _call(request, timeout, path)


def log(line: str) -> None:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n")
    except OSError:
        pass


def read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except ValueError:
        return {}


def context(event: str, text: str) -> None:
    if text:
        print(
            json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})
        )


def permission(decision: str, reason: str, text: str = "") -> None:
    """deny sends the action back to the agent with the reason; ask puts it to the person."""
    output = {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }
    if text:
        output["additionalContext"] = text
    print(json.dumps({"hookSpecificOutput": output}))


def send_back(reason: str) -> None:
    """A Stop hook's way of keeping the turn open: the agent reads the reason and goes on."""
    print(json.dumps({"decision": "block", "reason": reason}))


def run(hook: str, body) -> None:
    """A hook must never crash a session: whatever goes wrong is one line in the log and a
    silent exit 0. The action gate is the exception and says so itself."""
    try:
        body()
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001 - the one place a hook swallows everything
        log(hook + " " + type(error).__name__ + ": " + str(error)[:300])
        sys.exit(0)
