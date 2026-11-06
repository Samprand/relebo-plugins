"""Part 8, criterion 5: with the engine down every hook lets the session go on (exit 0) and
the agent reads one line saying what the memory did not do; the end of a turn says it to the
person; a command or a tool that only looks says nothing. Runs on the system python3:

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
TOKEN = "rlb_good"
# nothing listens on the discard port: the engine is down
DOWN = "http://127.0.0.1:9"


class _Busy(BaseHTTPRequestHandler):
    """An engine that answers every call with a 503, as when a row is held."""

    def log_message(self, *args) -> None:  # quiet
        return

    def do_POST(self) -> None:  # noqa: N802 - the server's name
        raw = json.dumps({"detail": {"code": "memory_busy", "message": "held"}}).encode()
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = do_POST


class UnreachedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.mkdtemp(prefix="relebo-home-")
        self.place = tempfile.mkdtemp(prefix="relebo-place-")
        os.environ["HOME"] = self.home
        os.environ["RELEBO_ENGINE_URL"] = DOWN
        os.environ["RELEBO_TOKEN"] = TOKEN
        for name in ("CLAUDE_PLUGIN_OPTION_TOKEN", "CLAUDE_PLUGIN_OPTION_ENGINE_URL", "RELEBO_CLIENT"):
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        os.environ.pop("RELEBO_TOKEN", None)

    def _hook(self, script: str, payload: dict) -> list:
        done = subprocess.run(
            [sys.executable, str(HOOKS / script)],
            input=json.dumps({"session_id": "s1", "cwd": self.place, **payload}),
            capture_output=True,
            text=True,
            env=dict(os.environ),
            timeout=30,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return [json.loads(line) for line in done.stdout.splitlines() if line.strip()]

    def _note(self, script: str, payload: dict, event: str) -> str:
        said = self._hook(script, payload)
        self.assertEqual(len(said), 1, said)
        out = said[0]["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], event)
        self.assertNotIn("\n", out["additionalContext"])
        return out["additionalContext"]

    def test_session_start_says_nothing_was_recalled(self) -> None:
        note = self._note("session_start.py", {"source": "startup"}, "SessionStart")
        self.assertIn("did not answer", note)

    def test_a_prompt_is_kept_and_the_agent_is_told(self) -> None:
        note = self._note("user_prompt.py", {"prompt": "el 8 descártalo"}, "UserPromptSubmit")
        self.assertIn("kept on this machine", note)
        sys.path.insert(0, str(HOOKS))
        sys.modules.pop("_client", None)
        client = importlib.import_module("_client")
        unread = client.read_json(client.MEMORY_DIR / "unread.json")
        self.assertEqual(unread.get("s1"), ["el 8 descártalo"])

    def test_an_edit_after_the_tool_is_said(self) -> None:
        target = str(Path(self.place) / "a.txt")
        payload = {"tool_name": "Write", "tool_input": {"file_path": target, "content": "x"}}
        self.assertIn("not recorded", self._note("post_tool.py", payload, "PostToolUse"))

    def test_a_command_that_only_looks_says_nothing(self) -> None:
        self.assertEqual(self._hook("post_tool.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}}), [])
        self.assertEqual(self._hook("post_tool.py", {"tool_name": "Read", "tool_input": {"file_path": "/x"}}), [])

    def test_the_end_of_a_turn_tells_the_person_and_does_not_keep_the_turn_open(self) -> None:
        said = self._hook("stop.py", {"last_assistant_message": "Hecho."})
        self.assertEqual(len(said), 1, said)
        self.assertIn("systemMessage", said[0])
        self.assertNotIn("decision", said[0])

    def test_a_busy_engine_is_said_the_same_way(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _Busy)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            os.environ["RELEBO_ENGINE_URL"] = "http://127.0.0.1:%d" % server.server_address[1]
            self._note("session_start.py", {"source": "startup"}, "SessionStart")
            self._note("user_prompt.py", {"prompt": "hola"}, "UserPromptSubmit")
        finally:
            server.shutdown()


class OneAnswerTest(unittest.TestCase):
    """A hook prints one JSON object: a note never follows an answer already given."""

    def setUp(self) -> None:
        sys.path.insert(0, str(HOOKS))
        sys.modules.pop("_client", None)
        self.client = importlib.import_module("_client")

    def test_a_crash_after_an_answer_adds_no_note(self) -> None:
        printed = []
        self.client._say = lambda output: (printed.append(output), self.client._said.__setitem__(0, True))

        def body() -> None:
            self.client.context("PostToolUse", "what the place remembers")
            raise RuntimeError("after the answer")

        with self.assertRaises(SystemExit):
            self.client.run("post_tool", body, "PostToolUse")
        self.assertEqual(len(printed), 1)

    def test_a_crash_before_any_answer_is_the_note(self) -> None:
        printed = []
        self.client._say = lambda output: (printed.append(output), self.client._said.__setitem__(0, True))

        def body() -> None:
            raise RuntimeError("before anything")

        with self.assertRaises(SystemExit):
            self.client.run("session_start", body, "SessionStart")
        self.assertEqual(
            printed[0]["hookSpecificOutput"]["additionalContext"],
            self.client.UNREACHED_NOTES["SessionStart"],
        )


if __name__ == "__main__":
    unittest.main()
