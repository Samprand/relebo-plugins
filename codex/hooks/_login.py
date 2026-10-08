"""How this device becomes the person: the OAuth device flow (RFC 8628). From the hooks, which
cannot open a browser: SessionStart asks the engine for a code and shows it; the person
approves it on the web with their ordinary session; UserPromptSubmit polls once per prompt
and keeps the token when it arrives. From /relebo:login (`--connect`): the browser opens on
the approval page with the code filled in, the line with the code and the address is shown
at once (closing the page loses nothing), and a watcher left behind (`--watch`) keeps the
token the moment the person approves; with no browser to open, the line alone does. A
token the person later revokes from Connections is thrown away the moment the engine refuses
it, and a new code is asked for right then, with the cause.

Also a script: `python3 _login.py --connect | --watch | --force | --status | --poll | --logout`."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client

DEVICE_CODE_PATH = "/auth/device/code"
DEVICE_TOKEN_PATH = "/auth/device/token"
SCOPE = "memory"

# OAuth answers while the person has not decided (RFC 8628 §3.5)
PENDING = "authorization_pending"
SLOW_DOWN = "slow_down"
EXPIRED = "expired_token"
DENIED = "access_denied"
# the code already handed out its token (spent), or is otherwise not a code of ours any more
SPENT = "invalid_grant"
# why the engine refused a token it was handed
TOKEN_REFUSALS = ("token_unknown", "token_revoked", "token_expired")
TOKEN_NO_PERSON = "token_no_person"

# the watcher /relebo:login leaves behind polls this often, for as long as the code lives
WATCH_POLL_S = 3.0
WATCH_MAX_S = 15 * 60.0

# what the person reads, one line each
SHOW_CODE = "Relebo: to connect this device, approve code %s at %s (the code lasts %d minutes)."
OPENED = (
    "Relebo: your browser opened to approve code %s. If it did not, or you closed it, open %s "
    "(the code lasts %d minutes). Once approved, this device is connected by itself."
)
WAITING = "Relebo is waiting for code %s at %s"
CONNECTED = "Relebo: this device is connected as you."
EXPIRED_LINE = "Relebo: the code expired. "
SPENT_LINE = "Relebo: that code was already used. "
CODE_REFUSED_LINE = "Relebo: could not get a login code from %s (%s). Type /relebo:login to retry."
DENIED_LINE = "Relebo: access denied. Type /relebo:login if that was a mistake"
REVOKED_LINE = "Relebo: this device was disconnected from Devices on %s. To come back in, approve %s at %s"
UNKNOWN_LINE = "Relebo: this device's token is no longer known to the engine. To come back in, approve %s at %s"
TOKEN_EXPIRED_LINE = "Relebo: this device's token expired. To come back in, approve %s at %s"
NO_PERSON_LINE = "Relebo: this token acts for no person; the memory needs one. Type /relebo:login to connect as you."
UNREACHED_LINE = "Relebo: the engine at %s did not answer; the memory is off until it does."
ENV_REVOKED_LINE = "Relebo: the token set in %s was revoked on %s; remove it to log in from the session."
ENV_REFUSED_LINE = "Relebo: the token set in %s is %s; remove it to log in from the session."
STATUS_CONNECTED = "Relebo: connected to %s (token from %s, device %s)."
STATUS_PENDING = "Relebo: not connected. " + WAITING
STATUS_NONE = "Relebo: not connected to %s. Type /relebo:login to get a code."
LOGGED_OUT = (
    "Relebo: this device forgot its token. If you did not revoke it from Devices on the web, "
    "do that too: the token itself still exists until you do."
)


def _now() -> float:
    return time.time()


def _interval(found: dict, fallback: int = 5) -> int:
    """The seconds between polls; zero is a real answer, so only a missing one falls back."""
    value = found.get("interval")
    return fallback if value is None else int(value)


def pending() -> dict:
    """The code asked for and not yet decided, if it still stands."""
    found = _client.read_json(_client.PENDING_FILE)
    if not found.get("device_code"):
        return {}
    if float(found.get("expires_at") or 0) <= _now():
        return {}
    return found


def denied_in(session_id: str) -> bool:
    """A refusal is respected for the session it happened in: nobody is asked twice."""
    found = _client.read_json(_client.PENDING_FILE)
    return bool(found.get("denied_in")) and found.get("denied_in") == session_id


def begin_at_session_start(session_id: str = "", opener=None, watcher=None) -> str:
    """What SessionStart shows with no identity: the code, and, the first time it is asked for,
    the browser opened on its approval page with a watcher behind, so a person who just
    installed the plugin only presses Authorize. A code already waiting is only repeated."""
    already = bool(pending())
    line = begin(session_id=session_id)
    waiting = pending()
    if already or not waiting or not line.startswith("Relebo: to connect"):
        return line
    where = waiting.get("verification_uri_complete") or waiting.get("verification_uri")
    minutes = max(1, int((float(waiting.get("expires_at") or 0) - _now()) / 60))
    (watcher or _watch_in_background)()
    if not (opener or _open_browser)(where):
        return line
    return OPENED % (waiting.get("user_code"), where, minutes)


def begin(force: bool = False, session_id: str = "") -> str:
    """Asks the engine for a code, or shows the one already waiting. Returns the line."""
    waiting = pending()
    if waiting and not force:
        return SHOW_CODE % (
            waiting.get("user_code"),
            waiting.get("verification_uri_complete") or waiting.get("verification_uri"),
            max(1, int((float(waiting.get("expires_at") or 0) - _now()) / 60)),
        )
    if not force and session_id and denied_in(session_id):
        return ""
    reply = _client.post_reply(
        DEVICE_CODE_PATH,
        {"client_id": _client.CLIENT_ID, "scope": SCOPE, "host_name": platform.node()},
        timeout=_client.LOGIN_TIMEOUT_S,
    )
    if not reply.ok:
        if reply.status == 0:
            return UNREACHED_LINE % _client.engine_url()
        _client.log("login: code refused " + str(reply.status) + " " + reply.error_code)
        return CODE_REFUSED_LINE % (_client.engine_url(), reply.error_code or reply.status)
    code = reply.body
    expires_in = int(code.get("expires_in") or 900)
    _client.write_json(
        _client.PENDING_FILE,
        {
            "device_code": code.get("device_code"),
            "user_code": code.get("user_code"),
            "verification_uri": code.get("verification_uri"),
            "verification_uri_complete": code.get("verification_uri_complete")
            or code.get("verification_uri"),
            "expires_at": _now() + expires_in,
            "interval": _interval(code),
            "engine_url": _client.engine_url(),
            "last_poll_at": 0,
        },
    )
    return SHOW_CODE % (
        code.get("user_code"),
        code.get("verification_uri_complete") or code.get("verification_uri"),
        max(1, expires_in // 60),
    )


def poll(session_id: str = "") -> str:
    """One poll of the code waiting, if its interval has passed. Returns the line to show,
    or "" when there is nothing to say."""
    waiting = pending()
    if not waiting:
        stale = _client.read_json(_client.PENDING_FILE)
        if stale.get("device_code"):
            # it ran out while nobody looked: a fresh one, said so
            _client.remove(_client.PENDING_FILE)
            return EXPIRED_LINE + begin(session_id=session_id)
        return ""
    where = waiting.get("verification_uri_complete") or waiting.get("verification_uri")
    if _now() - float(waiting.get("last_poll_at") or 0) < _interval(waiting):
        return WAITING % (waiting.get("user_code"), where)
    waiting["last_poll_at"] = _now()
    reply = _client.post_reply(
        DEVICE_TOKEN_PATH,
        {"client_id": _client.CLIENT_ID, "device_code": waiting.get("device_code")},
        timeout=_client.LOGIN_TIMEOUT_S,
    )
    if reply.ok and reply.body.get("access_token"):
        _client.write_json(
            _client.TOKEN_FILE,
            {
                "access_token": reply.body["access_token"],
                "engine_url": waiting.get("engine_url") or _client.engine_url(),
                "client_id": _client.CLIENT_ID,
                "name": platform.node(),
                "obtained_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        _client.remove(_client.PENDING_FILE)
        return CONNECTED
    code = reply.error_code
    if code == SLOW_DOWN:
        waiting["interval"] = _interval(waiting) + 5
    if code in (PENDING, SLOW_DOWN) or reply.status == 0:
        _client.write_json(_client.PENDING_FILE, waiting)
        return WAITING % (waiting.get("user_code"), where)
    if code == EXPIRED:
        _client.remove(_client.PENDING_FILE)
        return EXPIRED_LINE + begin(session_id=session_id)
    if code == SPENT:
        # the token was already handed out: a device that has it says nothing; one that lost
        # it asks for a new code
        _client.remove(_client.PENDING_FILE)
        if _client.identified():
            return ""
        return SPENT_LINE + begin(session_id=session_id)
    if code == DENIED:
        _client.write_json(_client.PENDING_FILE, {"denied_in": session_id, "denied_at": _now()})
        return DENIED_LINE
    _client.log("login: poll answered " + str(reply.status) + " " + code)
    _client.write_json(_client.PENDING_FILE, waiting)
    return WAITING % (waiting.get("user_code"), where)


def _open_browser(url: str) -> bool:
    """Opens the approval page in the person's browser; False where there is none to open
    (a shell over SSH, a Linux box with no display, RELEBO_NO_BROWSER set)."""
    if os.environ.get("RELEBO_NO_BROWSER") or os.environ.get("SSH_CONNECTION"):
        return False
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:  # noqa: BLE001 - whatever the platform's opener raises, it did not open
        return False


def _watch_in_background() -> bool:
    """A process of its own that keeps the token the moment the code is approved, so the
    command returns at once and the person has nothing more to do here."""
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--watch"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def connect(opener=None, watcher=None) -> str:
    """What /relebo:login does: a fresh code, the browser opened on its approval page, a
    watcher left behind to keep the token, and one line back at once with the code and the
    address, so closing the page loses nothing."""
    begun = begin(force=True)
    waiting = pending()
    if not waiting:
        return begun
    where = waiting.get("verification_uri_complete") or waiting.get("verification_uri")
    minutes = max(1, int((float(waiting.get("expires_at") or 0) - _now()) / 60))
    (watcher or _watch_in_background)()
    if not (opener or _open_browser)(where):
        return begun
    return OPENED % (waiting.get("user_code"), where, minutes)


def watch(max_s: float = WATCH_MAX_S, sleeper=time.sleep) -> str:
    """Polls the code waiting until it is decided or dies; the token lands in its file the
    moment it is approved. The line it ends on is for a log, nobody reads it."""
    deadline = _now() + max_s
    while _now() < deadline:
        sleeper(WATCH_POLL_S)
        line = poll()
        if line == CONNECTED or line == DENIED_LINE or not pending():
            return line
    return ""


def refused(reply: _client.Reply) -> bool:
    """Whether the engine turned the token itself away, as opposed to failing the call."""
    return reply.status == 401 and reply.error_code in TOKEN_REFUSALS + (TOKEN_NO_PERSON,)


def _source_name(source: str) -> str:
    return "the plugin option" if source == "option" else "RELEBO_TOKEN"


def forget(reply: _client.Reply, session_id: str = "") -> str:
    """The token is gone: thrown away here, and a new code asked for right then, with the
    cause said in one line. A token that acts for no person is not this device's to throw,
    and neither is one set in the plugin's option or RELEBO_TOKEN: the person is told to
    remove it, since a code approved here could never win over it."""
    code = reply.error_code
    if code == TOKEN_NO_PERSON:
        return NO_PERSON_LINE
    source = _client.token_source()
    if source in ("option", "env"):
        if code == "token_revoked":
            return ENV_REVOKED_LINE % (_source_name(source), _day(reply.detail.get("revoked_at")))
        cause = "expired" if code == "token_expired" else "no longer known to the engine"
        return ENV_REFUSED_LINE % (_source_name(source), cause)
    _client.remove(_client.TOKEN_FILE)
    if not pending():
        # nothing valid waits (or only a refusal from an earlier session): start clean
        _client.remove(_client.PENDING_FILE)
    begin(session_id=session_id)
    waiting = pending()
    user_code = waiting.get("user_code") or "a new code"
    where = (
        waiting.get("verification_uri_complete")
        or waiting.get("verification_uri")
        or _client.engine_url()
    )
    if code == "token_revoked":
        return REVOKED_LINE % (_day(reply.detail.get("revoked_at")), user_code, where)
    if code == "token_expired":
        return TOKEN_EXPIRED_LINE % (user_code, where)
    return UNKNOWN_LINE % (user_code, where)


def _day(value) -> str:
    """An ISO instant as the person would say it: "Oct 7"."""
    if not value:
        return "an earlier date"
    text = str(value).replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return str(value)[:10]
    if when.tzinfo is not None:
        when = when.astimezone()
    return when.strftime("%b") + " " + str(when.day)


def status() -> str:
    if _client.identified():
        kept = _client.read_json(_client.TOKEN_FILE)
        source = _client.token_source()
        source_name = str(_client.TOKEN_FILE) if source == "file" else _source_name(source or "")
        return STATUS_CONNECTED % (
            _client.engine_url(),
            source_name,
            kept.get("name") or platform.node(),
        )
    waiting = pending()
    if waiting:
        return STATUS_PENDING % (
            waiting.get("user_code"),
            waiting.get("verification_uri_complete") or waiting.get("verification_uri"),
        )
    return STATUS_NONE % _client.engine_url()


def logout() -> str:
    _client.remove(_client.TOKEN_FILE)
    _client.remove(_client.PENDING_FILE)
    return LOGGED_OUT


# words in the person's own ask that mean "just tell me where I stand"
STATUS_WORDS = ("status", "estado", "connected", "conectado", "conectada")


def command(arguments: str) -> str:
    """What /relebo:login prints: the state when the person asked for it, the connection
    otherwise. The command's own words decide, so no model has to."""
    words = arguments.lower()
    if any(word in words for word in STATUS_WORDS):
        return status()
    return connect()


def main(argv: list) -> int:
    if "--command" in argv:
        print(command(" ".join(argv[argv.index("--command") + 1 :])))
        return 0
    if "--status" in argv:
        print(status())
    elif "--logout" in argv:
        print(logout())
    elif "--poll" in argv:
        print(poll() or status())
    elif "--connect" in argv:
        print(connect())
    elif "--watch" in argv:
        watch()
    else:
        print(begin(force="--force" in argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
