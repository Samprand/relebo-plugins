"""The memory reads the person's words alone. What the harness writes in the person's turn
and the person never typed (a subagent's report handed back, a background task's notice, a
message from another session) is not sent (2026-11-14: a subagent's route map became
fourteen «whose» questions in the person's Pendientes)."""

import sys
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

import user_prompt  # noqa: E402


class UserPromptTest(unittest.TestCase):
    def test_the_persons_words_are_theirs(self) -> None:
        self.assertTrue(user_prompt.said_by_the_person("quiero que cada vez que alguien me pida"))
        self.assertTrue(user_prompt.said_by_the_person("Si"))

    def test_what_the_harness_relays_is_not_the_persons(self) -> None:
        relayed = (
            '<agent-message from="a367d5190ddb4a843">\n[Subagent hand-back] The text below',
            "[SYSTEM NOTIFICATION - NOT USER INPUT]\nThis is an automated background-task",
            "<task-notification>\n<task-id>abc</task-id>",
        )
        for text in relayed:
            self.assertFalse(user_prompt.said_by_the_person(text), text[:30])

    def test_a_relayed_message_is_not_posted_to_the_memory(self) -> None:
        posted = []
        client, unread = user_prompt._client, user_prompt._unread
        saved = (client.identified, client.post_reply, client.log, unread.flush)
        client.identified = lambda: True
        client.post_reply = lambda path, body, timeout=0: posted.append(path)
        client.log = lambda line: None
        unread.flush = lambda session_id, place: None
        relayed = '<agent-message from="x">\n[Subagent hand-back] ...'
        try:
            user_prompt.talk({"session_id": "s", "cwd": "/tmp", "prompt": relayed})
        finally:
            client.identified, client.post_reply, client.log, unread.flush = saved
        self.assertEqual(posted, [])


if __name__ == "__main__":
    unittest.main()
