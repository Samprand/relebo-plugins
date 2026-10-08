"""The device flow from the hooks' side, against a stub engine: a code is asked and shown, the
token lands when approved, an expired code is replaced, a refusal is respected, and a token the
person revoked is thrown away with the cause said. Runs on the system python3:

    python3 -m unittest discover plugins/claude-code/relebo/tests
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
REVOKED_AT = "2026-10-07T10:00:00+00:00"
GOOD_TOKEN = "rlb_good"


class _Engine(BaseHTTPRequestHandler):
    """A stub of the engine's door: what it answers is set per test through `state`."""

    state = {"mode": "pending", "codes": 0, "polls": 0}

    def log_message(self, *args) -> None:  # quiet
        return

    def _json(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self) -> None:  # noqa: N802 - the server's name
        state = _Engine.state
        if self.path == "/auth/device/code":
            if state.get("code_mode") == "refused":
                self._json(400, {"error": "invalid_client", "error_description": "who"})
                return
            state["codes"] += 1
            state["last_client"] = self._body().get("client_id")
            code = "WDJB-MJH" + str(state["codes"])
            self._json(
                200,
                {
                    "device_code": "dev-" + str(state["codes"]),
                    "user_code": code,
                    "verification_uri": "https://relebo.test/device",
                    "verification_uri_complete": "https://relebo.test/device?code=" + code,
                    "expires_in": 900,
                    "interval": 0,
                },
            )
            return
        if self.path == "/auth/device/token":
            state["polls"] += 1
            mode = state["mode"]
            if mode == "approved":
                self._json(200, {"access_token": GOOD_TOKEN, "token_type": "Bearer", "expires_in": None, "scope": "memory"})
            elif mode in ("expired_token", "access_denied", "slow_down", "authorization_pending", "invalid_grant"):
                self._json(400, {"error": mode, "error_description": mode})
            else:
                self._json(400, {"error": "authorization_pending", "error_description": "nobody yet"})
            return
        if self.path.startswith("/memory/sessions/"):
            if self.headers.get("Authorization") == "Bearer " + GOOD_TOKEN:
                self._json(200, {"context": "what the place remembers", "standing_id": None})
            else:
                self._json(
                    401,
                    {"detail": {"code": state.get("refusal", "token_revoked"), "message": "revoked", "revoked_at": REVOKED_AT}},
                )
            return
        self._json(404, {"detail": "no such route"})

    do_GET = do_POST


class LoginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), _Engine)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def setUp(self) -> None:
        self.home = tempfile.mkdtemp(prefix="relebo-home-")
        os.environ["HOME"] = self.home
        os.environ["RELEBO_ENGINE_URL"] = self.url
        for name in ("CLAUDE_PLUGIN_OPTION_TOKEN", "RELEBO_TOKEN", "CLAUDE_PLUGIN_OPTION_ENGINE_URL", "RELEBO_CLIENT"):
            os.environ.pop(name, None)
        _Engine.state = {"mode": "pending", "codes": 0, "polls": 0}
        sys.path.insert(0, str(HOOKS))
        for name in ("_client", "_login"):
            sys.modules.pop(name, None)
        self.client = importlib.import_module("_client")
        self.login = importlib.import_module("_login")

    def test_begin_shows_the_code_and_keeps_it_pending(self) -> None:
        line = self.login.begin()
        self.assertIn("WDJB-MJH1", line)
        self.assertIn("https://relebo.test/device?code=WDJB-MJH1", line)
        self.assertIn("15 minutes", line)
        kept = json.loads(self.client.PENDING_FILE.read_text())
        self.assertEqual(kept["device_code"], "dev-1")
        self.assertEqual(oct(self.client.PENDING_FILE.stat().st_mode)[-3:], "600")
        # asked again without force: the same code, not a new one
        self.assertIn("WDJB-MJH1", self.login.begin())
        self.assertEqual(_Engine.state["codes"], 1)
        self.assertEqual(_Engine.state["last_client"], "claude-code")

    def test_poll_waits_then_lands_the_token(self) -> None:
        self.login.begin()
        self.assertEqual(self.login.poll(), "Relebo is waiting for code WDJB-MJH1 at https://relebo.test/device?code=WDJB-MJH1")
        _Engine.state["mode"] = "approved"
        self.assertEqual(self.login.poll(), self.login.CONNECTED)
        kept = json.loads(self.client.TOKEN_FILE.read_text())
        self.assertEqual(kept["access_token"], GOOD_TOKEN)
        self.assertEqual(kept["engine_url"], self.url)
        self.assertEqual(kept["client_id"], "claude-code")
        self.assertFalse(self.client.PENDING_FILE.exists())
        self.assertTrue(self.client.identified())

    def test_expired_code_is_replaced_and_said(self) -> None:
        self.login.begin()
        _Engine.state["mode"] = "expired_token"
        line = self.login.poll()
        self.assertTrue(line.startswith("Relebo: the code expired. "))
        self.assertIn("WDJB-MJH2", line)
        self.assertEqual(json.loads(self.client.PENDING_FILE.read_text())["device_code"], "dev-2")

    def test_denied_stops_asking_in_that_session(self) -> None:
        self.login.begin(session_id="s1")
        _Engine.state["mode"] = "access_denied"
        self.assertEqual(self.login.poll("s1"), self.login.DENIED_LINE)
        self.assertEqual(self.login.begin(session_id="s1"), "")
        self.assertEqual(self.login.poll("s1"), "")
        # another session, or /relebo:login, asks again
        self.assertIn("WDJB-MJH2", self.login.begin(session_id="s2"))

    def test_revoked_token_is_thrown_away_with_the_cause(self) -> None:
        self.client.write_json(self.client.TOKEN_FILE, {"access_token": "rlb_old", "engine_url": self.url})
        self.assertTrue(self.client.identified())
        reply = self.client.post_reply("/memory/sessions/arrive", {"origin_id": "s1"})
        self.assertTrue(self.login.refused(reply))
        line = self.login.forget(reply, "s1")
        self.assertEqual(
            line,
            "Relebo: this device was disconnected from Devices on Oct 7. To come back in, approve WDJB-MJH1 at https://relebo.test/device?code=WDJB-MJH1",
        )
        self.assertFalse(self.client.TOKEN_FILE.exists())
        self.assertFalse(self.client.identified())
        self.assertTrue(self.client.PENDING_FILE.exists())

    def test_unknown_token_names_its_own_cause(self) -> None:
        _Engine.state["refusal"] = "token_unknown"
        self.client.write_json(self.client.TOKEN_FILE, {"access_token": "rlb_old", "engine_url": self.url})
        reply = self.client.post_reply("/memory/sessions/arrive", {"origin_id": "s1"})
        self.assertTrue(self.login.forget(reply).startswith("Relebo: this device's token is no longer known"))

    def test_revoked_token_from_env_is_not_thrown_away_and_no_code_is_asked(self) -> None:
        os.environ["RELEBO_TOKEN"] = "rlb_env"
        self.assertEqual(self.client.token_source(), "env")
        reply = self.client.post_reply("/memory/sessions/arrive", {"origin_id": "s1"})
        line = self.login.forget(reply, "s1")
        self.assertEqual(
            line,
            "Relebo: the token set in RELEBO_TOKEN was revoked on Oct 7; remove it to log in from the session.",
        )
        self.assertEqual(_Engine.state["codes"], 0)
        self.assertFalse(self.client.PENDING_FILE.exists())
        # the same for the plugin's option, and for a cause other than revocation
        os.environ.pop("RELEBO_TOKEN")
        os.environ["CLAUDE_PLUGIN_OPTION_TOKEN"] = "rlb_opt"
        _Engine.state["refusal"] = "token_unknown"
        reply = self.client.post_reply("/memory/sessions/arrive", {"origin_id": "s1"})
        self.assertEqual(
            self.login.forget(reply, "s1"),
            "Relebo: the token set in the plugin option is no longer known to the engine; remove it to log in from the session.",
        )
        self.assertEqual(_Engine.state["codes"], 0)

    def test_revoked_file_token_reuses_the_code_already_waiting(self) -> None:
        self.login.begin(session_id="s1")
        self.client.write_json(self.client.TOKEN_FILE, {"access_token": "rlb_old", "engine_url": self.url})
        self.assertEqual(self.client.token_source(), "file")
        reply = self.client.post_reply("/memory/sessions/arrive", {"origin_id": "s1"})
        line = self.login.forget(reply, "s1")
        self.assertIn("approve WDJB-MJH1 at", line)
        self.assertEqual(_Engine.state["codes"], 1)
        self.assertFalse(self.client.TOKEN_FILE.exists())

    def test_a_refused_code_request_is_said(self) -> None:
        _Engine.state["code_mode"] = "refused"
        line = self.login.begin()
        self.assertEqual(
            line,
            "Relebo: could not get a login code from %s (invalid_client). Type /relebo:login to retry." % self.url,
        )
        self.assertFalse(self.client.PENDING_FILE.exists())

    def test_spent_code_is_dropped(self) -> None:
        # without a token: a new code, said
        self.login.begin()
        _Engine.state["mode"] = "invalid_grant"
        line = self.login.poll()
        self.assertTrue(line.startswith("Relebo: that code was already used. "))
        self.assertIn("WDJB-MJH2", line)
        # with the token in hand: the stale pending code goes quietly
        self.client.write_json(self.client.TOKEN_FILE, {"access_token": GOOD_TOKEN, "engine_url": self.url})
        self.assertEqual(self.login.poll(), "")
        self.assertFalse(self.client.PENDING_FILE.exists())
        self.assertEqual(_Engine.state["codes"], 2)

    def test_connect_opens_the_browser_says_the_link_and_leaves_a_watcher(self) -> None:
        opened, watched = [], []
        line = self.login.connect(opener=lambda url: opened.append(url) or True, watcher=lambda: watched.append(1) or True)
        self.assertEqual(opened, ["https://relebo.test/device?code=WDJB-MJH1"])
        self.assertEqual(watched, [1])
        self.assertIn("browser opened to approve code WDJB-MJH1", line)
        self.assertIn("https://relebo.test/device?code=WDJB-MJH1", line)
        self.assertTrue(self.client.PENDING_FILE.exists())
        self.assertEqual(_Engine.state["polls"], 0)

    def test_connect_without_a_browser_shows_the_code_at_once(self) -> None:
        line = self.login.connect(opener=lambda url: False, watcher=lambda: True)
        self.assertIn("approve code WDJB-MJH1 at https://relebo.test/device?code=WDJB-MJH1", line)
        self.assertEqual(_Engine.state["polls"], 0)

    def test_the_watcher_keeps_the_token_once_approved_and_stops(self) -> None:
        self.login.begin()
        polls = []

        def sleeper(seconds):
            polls.append(seconds)
            if len(polls) == 2:
                _Engine.state["mode"] = "approved"

        self.assertEqual(self.login.watch(max_s=60, sleeper=sleeper), self.login.CONNECTED)
        self.assertEqual(len(polls), 2)
        self.assertTrue(self.client.identified())

    def test_the_watcher_stops_on_a_refusal_and_when_the_code_dies(self) -> None:
        self.login.begin()
        _Engine.state["mode"] = "access_denied"
        self.assertEqual(self.login.watch(max_s=60, sleeper=lambda s: None), self.login.DENIED_LINE)
        clock = [0.0]
        self.login._now = lambda: clock[0]
        self.login.begin(force=True)
        _Engine.state["mode"] = "pending"

        def sleeper(seconds):
            clock[0] += seconds

        self.assertEqual(self.login.watch(max_s=10, sleeper=sleeper), "")

    def test_the_command_tells_status_from_connect_by_the_persons_words(self) -> None:
        self.assertIn("not connected", self.login.command("status"))
        self.assertIn("not connected", self.login.command("¿estoy conectado?"))
        self.assertEqual(_Engine.state["codes"], 0)
        os.environ["RELEBO_NO_BROWSER"] = "1"
        self.login._watch_in_background = lambda: True
        try:
            line = self.login.command("")
        finally:
            os.environ.pop("RELEBO_NO_BROWSER", None)
        self.assertIn("approve code WDJB-MJH1", line)

    def test_read_payload_survives_a_broken_stdin(self) -> None:
        class _Broken:
            def read(self, *args):
                raise OSError("stdin is gone")

        kept = sys.stdin
        try:
            sys.stdin = _Broken()
            self.assertEqual(self.client.read_payload(), {})
        finally:
            sys.stdin = kept

    def test_gate_answers_ask_on_a_stdin_that_is_not_json(self) -> None:
        self.client.write_json(self.client.TOKEN_FILE, {"access_token": GOOD_TOKEN, "engine_url": self.url})
        done = subprocess.run(
            [sys.executable, str(HOOKS / "pre_tool.py")],
            input="not json at all",
            capture_output=True,
            text=True,
            env=dict(os.environ),
            timeout=30,
            check=False,
        )
        # an empty payload names no tool: the gate has nothing to judge and lets it through
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_slow_down_widens_the_interval(self) -> None:
        self.login.begin()
        _Engine.state["mode"] = "slow_down"
        self.login.poll()
        self.assertEqual(json.loads(self.client.PENDING_FILE.read_text())["interval"], 5)

    def test_engine_unreached_is_one_line_and_no_file(self) -> None:
        os.environ["RELEBO_ENGINE_URL"] = "http://127.0.0.1:9"
        self.assertTrue(self.login.begin().startswith("Relebo: the engine at http://127.0.0.1:9 did not answer"))
        self.assertFalse(self.client.PENDING_FILE.exists())

    def test_codex_client_id_travels(self) -> None:
        os.environ["RELEBO_CLIENT"] = "codex"
        sys.modules.pop("_client", None)
        sys.modules.pop("_login", None)
        login = importlib.import_module("_login")
        login.begin()
        self.assertEqual(_Engine.state["last_client"], "codex")

    def _hook(self, script: str, payload: dict) -> dict:
        done = subprocess.run(
            [sys.executable, str(HOOKS / script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=dict(os.environ),
            timeout=30,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else {}

    def test_session_start_shows_the_code_and_user_prompt_connects(self) -> None:
        out = self._hook("session_start.py", {"session_id": "s1", "cwd": self.home, "source": "startup"})
        text = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("approve code WDJB-MJH1", text)
        _Engine.state["mode"] = "approved"
        out = self._hook("user_prompt.py", {"session_id": "s1", "cwd": self.home, "prompt": "hola"})
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], self.login.CONNECTED)
        self.assertTrue(self.client.TOKEN_FILE.exists())
        # connected: the next prompt reaches the memory as the person
        out = self._hook("user_prompt.py", {"session_id": "s1", "cwd": self.home, "prompt": "hola"})
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], "what the place remembers")

    def test_session_start_after_revocation_shows_the_cause(self) -> None:
        self.client.write_json(self.client.TOKEN_FILE, {"access_token": "rlb_old", "engine_url": self.url})
        out = self._hook("session_start.py", {"session_id": "s1", "cwd": self.home, "source": "startup"})
        self.assertIn("disconnected from Devices on Oct 7", out["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(self.client.TOKEN_FILE.exists())

    def test_script_status_and_logout(self) -> None:
        done = subprocess.run([sys.executable, str(HOOKS / "_login.py"), "--status"], capture_output=True, text=True, env=dict(os.environ), check=False)
        self.assertIn("not connected", done.stdout)
        subprocess.run([sys.executable, str(HOOKS / "_login.py"), "--force"], capture_output=True, text=True, env=dict(os.environ), check=False)
        self.assertTrue(self.client.PENDING_FILE.exists())
        done = subprocess.run([sys.executable, str(HOOKS / "_login.py"), "--logout"], capture_output=True, text=True, env=dict(os.environ), check=False)
        self.assertIn("forgot its token", done.stdout)
        self.assertFalse(self.client.PENDING_FILE.exists())
        self.client.write_json(self.client.TOKEN_FILE, {"access_token": GOOD_TOKEN, "engine_url": self.url, "name": "Julians-MacBook"})
        done = subprocess.run([sys.executable, str(HOOKS / "_login.py"), "--status"], capture_output=True, text=True, env=dict(os.environ), check=False)
        self.assertEqual(
            done.stdout.strip(),
            "Relebo: connected to %s (token from %s, device Julians-MacBook)." % (self.url, self.client.TOKEN_FILE),
        )


if __name__ == "__main__":
    unittest.main()
