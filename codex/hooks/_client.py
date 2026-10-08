"""What every hook of the Relebo plugin shares: who this device is to the engine, how it
posts, and where it keeps what is only this device's. Stdlib only: hooks run on the system
python3, which may be 3.9, so annotations stay postponed.

Identity is a Relebo token (rlb_…) the person approved once from the web, kept in
~/.relebo/token.json. A plugin option or RELEBO_TOKEN wins over the file. Nothing else: the
desktop app's machine key is gone."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

RELEBO_DIR = Path.home() / ".relebo"
# the token the person approved for this device, and the engine it was approved at
TOKEN_FILE = RELEBO_DIR / "token.json"
# a code asked for and not yet decided: what to poll and what to show the person meanwhile
PENDING_FILE = RELEBO_DIR / "device.json"
MEMORY_DIR = RELEBO_DIR / "memory"
LOG_FILE = MEMORY_DIR / "hooks.log"
PLACES_FILE = MEMORY_DIR / "places.json"
# the hosted engine; a device that never installed anything of Relebo reaches this one
DEFAULT_ENGINE = "https://api.relebo.ai"
# which of Relebo's own clients these hooks run as: Codex sets RELEBO_CLIENT=codex
CLIENT_ID = os.environ.get("RELEBO_CLIENT") or "claude-code"
TIMEOUT_S = 60.0
# a hook that gates an action waits less: the person is waiting on the other side
GATE_TIMEOUT_S = 25.0
# asking for a code or polling it must never make a session start slow
LOGIN_TIMEOUT_S = 10.0


def read_json(path: Path) -> dict:
    try:
        found = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def write_json(path: Path, data: dict) -> None:
    """Only this user may read it, and a crash mid-write leaves the old file, not half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(json.dumps(data, indent=2, sort_keys=True))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def token() -> str:
    return (
        os.environ.get("CLAUDE_PLUGIN_OPTION_TOKEN")
        or os.environ.get("RELEBO_TOKEN")
        or read_json(TOKEN_FILE).get("access_token", "")
    )


def token_source() -> str | None:
    """Where the token in use comes from: "option" (the plugin's setting), "env"
    (RELEBO_TOKEN), "file" (token.json), or None when there is none. A token set outside
    this device's files is not this device's to throw away."""
    if os.environ.get("CLAUDE_PLUGIN_OPTION_TOKEN"):
        return "option"
    if os.environ.get("RELEBO_TOKEN"):
        return "env"
    if read_json(TOKEN_FILE).get("access_token"):
        return "file"
    return None


def engine_url() -> str:
    return (
        os.environ.get("CLAUDE_PLUGIN_OPTION_ENGINE_URL")
        or os.environ.get("RELEBO_ENGINE_URL")
        or read_json(TOKEN_FILE).get("engine_url")
        or read_json(PENDING_FILE).get("engine_url")
        or DEFAULT_ENGINE
    ).rstrip("/")


def headers() -> dict:
    found = {"Content-Type": "application/json"}
    bearer = token()
    if bearer:
        found["Authorization"] = "Bearer " + bearer
    return found


def identified() -> bool:
    return bool(token())


class Reply:
    """What the engine answered: the status, the body when it was JSON, and the code a
    refusal carried. Status 0 means the engine was not reached at all."""

    def __init__(self, status: int, body) -> None:
        self.status = status
        self.body = body if isinstance(body, dict) else None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.body is not None

    @property
    def detail(self) -> dict:
        """A refusal's detail: {"code", "message", ...} however FastAPI wrapped it."""
        if not self.body:
            return {}
        detail = self.body.get("detail")
        if isinstance(detail, dict):
            return detail
        if isinstance(detail, str):
            return {"code": "", "message": detail}
        return self.body

    @property
    def error_code(self) -> str:
        """An OAuth error ("authorization_pending") or a refused token's cause ("token_revoked")."""
        return str(self.body.get("error") or self.detail.get("code") or "") if self.body else ""


def _call(request: urllib.request.Request, timeout: float, path: str) -> Reply:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Reply(response.status, _parse(response.read()))
    except urllib.error.HTTPError as error:
        body = _parse(error.read())
        log("call " + path + " answered " + str(error.code) + ": " + json.dumps(body)[:300])
        return Reply(error.code, body)
    except (urllib.error.URLError, ValueError, OSError) as error:
        log("call " + path + " failed: " + str(error)[:300])
        return Reply(0, None)


def _parse(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        return {}


def post_reply(path: str, body: dict, timeout: float = TIMEOUT_S) -> Reply:
    data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    request = urllib.request.Request(
        engine_url() + path, data=data, headers=headers(), method="POST"
    )
    return _call(request, timeout, path)


def get_reply(path: str, timeout: float = TIMEOUT_S) -> Reply:
    request = urllib.request.Request(engine_url() + path, headers=headers(), method="GET")
    return _call(request, timeout, path)


def post(path: str, body: dict, timeout: float = TIMEOUT_S) -> dict | None:
    """POST to the engine; None on any failure. Hooks never raise."""
    reply = post_reply(path, body, timeout)
    return reply.body if reply.ok else None


def get(path: str, timeout: float = TIMEOUT_S) -> dict | None:
    reply = get_reply(path, timeout)
    return reply.body if reply.ok else None


def log(line: str) -> None:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n")
    except OSError:
        pass


def read_payload() -> dict:
    """What Claude Code handed the hook; a stdin that is not JSON, or not there, is empty."""
    try:
        found = json.load(sys.stdin)
    except (ValueError, OSError):
        return {}
    return found if isinstance(found, dict) else {}


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
