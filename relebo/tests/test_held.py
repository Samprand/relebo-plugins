"""A held action sent again unchanged is a repeat; changed by one character, it is not
(Part 8, criterion 4). The device keeps only the last held action of each session."""

import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

import _client  # noqa: E402
import _held  # noqa: E402


class HeldTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = _held.HELD_FILE
        _held.HELD_FILE = Path(self.tmp.name) / "held.json"
        self.action = {
            "tool": "Write",
            "path": "apps/api/src/tools/caller.ts",
            "written": ["export class Caller {}"],
        }

    def tearDown(self) -> None:
        _held.HELD_FILE = self.previous
        self.tmp.cleanup()

    def test_the_same_action_again_repeats_and_one_character_changed_does_not(self) -> None:
        self.assertFalse(_held.repeats("s1", self.action))
        _held.note("s1", self.action)
        self.assertTrue(_held.repeats("s1", self.action))
        changed = {**self.action, "written": ["export class Caller  {}"]}
        self.assertFalse(_held.repeats("s1", changed))
        self.assertFalse(_held.repeats("s2", self.action))

    def test_only_the_last_held_action_of_a_session_is_kept(self) -> None:
        _held.note("s1", self.action)
        other = {"tool": "Bash", "command": "pnpm run deploy", "written": []}
        _held.note("s1", other)
        self.assertFalse(_held.repeats("s1", self.action))
        self.assertTrue(_held.repeats("s1", other))
        _held.forget("s1")
        self.assertFalse(_held.repeats("s1", other))
        self.assertEqual(_client.read_json(_held.HELD_FILE), {})


if __name__ == "__main__":
    unittest.main()
