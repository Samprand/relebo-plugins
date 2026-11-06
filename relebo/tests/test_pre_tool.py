"""What the gate answers becomes Claude Code's permission decision (Part 8): a hold goes back
to the agent as a denial with the rule, the correction and a note to repeat; a prohibition is
denied; an exempt ban is put to the person with "ask", in their own terminal, and is not kept
as a held action the agent could repeat past (Part 4, decided 2026-11-06)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

import _client  # noqa: E402
import _held  # noqa: E402
import pre_tool  # noqa: E402


class PreToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (
            _held.HELD_FILE,
            _client.identified,
            _client.post_reply,
            pre_tool._situation.action_of,
        )
        _held.HELD_FILE = Path(self.tmp.name) / "held.json"
        _client.identified = lambda: True
        pre_tool._situation.action_of = lambda payload: {
            "tool": "Bash",
            "command": payload["tool_input"]["command"],
        }
        self.payload = {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "pnpm run deploy"},
            "cwd": self.tmp.name,
        }

    def tearDown(self) -> None:
        (
            _held.HELD_FILE,
            _client.identified,
            _client.post_reply,
            pre_tool._situation.action_of,
        ) = self.saved
        self.tmp.cleanup()

    def judged(self, answer: dict) -> dict:
        _client.post_reply = lambda path, body, timeout=0: _client.Reply(200, answer)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pre_tool.judge(self.payload)
        return json.loads(out.getvalue())["hookSpecificOutput"]

    def test_an_exempt_ban_is_put_to_the_person_and_is_not_kept_as_held(self) -> None:
        reason = "- nadie despliega a producción (tienes exención: confirma antes de seguir)"
        output = self.judged({"decision": "ask", "reason": reason})
        self.assertEqual(output["permissionDecision"], "ask")
        self.assertEqual(output["permissionDecisionReason"], reason)
        action = {"tool": "Bash", "command": "pnpm run deploy"}
        self.assertFalse(_held.repeats("s1", action))

    def test_a_hold_is_a_denial_to_the_agent_kept_for_the_repeat_and_a_ban_denies(self) -> None:
        output = self.judged({"decision": "hold", "reason": "- regla"})
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertTrue(_held.repeats("s1", {"tool": "Bash", "command": "pnpm run deploy"}))
        output = self.judged({"decision": "deny", "reason": "Prohibido"})
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertTrue(output["permissionDecisionReason"].startswith(pre_tool.DENIED))


if __name__ == "__main__":
    unittest.main()
