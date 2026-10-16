"""Every call of the plugin says who it is: Cloudflare refuses Python's default user agent
("Python-urllib/3.9") with a 403 before the engine sees the call (2026-10-15)."""

import sys
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

import _client  # noqa: E402


class Headers(unittest.TestCase):
    def test_every_call_names_the_plugin_and_its_client(self) -> None:
        agent = _client.headers()["User-Agent"]
        self.assertTrue(agent.startswith("Relebo/"), agent)
        self.assertIn("(" + _client.CLIENT_ID + ")", agent)
        self.assertNotIn("urllib", agent.lower())

    def test_the_version_is_the_manifest_s(self) -> None:
        self.assertRegex(_client.version(), r"^\d+\.\d+\.\d+$")
