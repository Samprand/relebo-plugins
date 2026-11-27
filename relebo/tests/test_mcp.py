"""The plugin's MCP server: the memory's calls as tools, carried to the engine with the
session the hooks noted for the folder."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import _client  # noqa: E402
import mcp  # noqa: E402


class McpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (
            _client.SESSIONS_DIR,
            _client.identified,
            _client.post_reply,
            _client.get_reply,
        )
        _client.SESSIONS_DIR = Path(self.tmp.name) / "sessions"
        _client.identified = lambda: True
        self.sent = []

        def post(path, body, timeout=0):
            self.sent.append((path, body))
            return _client.Reply(200, {"context": "guardada (hecho): x"})

        _client.post_reply = post
        self.work_tools = _client.Reply(0, None)
        _client.get_reply = lambda path, timeout=0: self.work_tools

    def tearDown(self) -> None:
        (
            _client.SESSIONS_DIR,
            _client.identified,
            _client.post_reply,
            _client.get_reply,
        ) = self.saved
        self.tmp.cleanup()

    def rpc(self, requests: list, cwd: str = "/work/relebo") -> list:
        stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
        stdout = io.StringIO()
        mcp.serve(stdin, stdout, cwd)
        return [json.loads(line) for line in stdout.getvalue().splitlines()]

    def test_initialize_lists_the_three_tools(self) -> None:
        [init, listed] = self.rpc(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ]
        )
        assert init["result"]["serverInfo"]["name"] == "relebo"
        assert [t["name"] for t in listed["result"]["tools"]] == [
            "remember",
            "search_memories",
            "report_memory_issue",
        ]

    def test_remember_carries_the_folders_session_and_the_fields(self) -> None:
        _client.note_session("/work/relebo", "s-77")
        [reply] = self.rpc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "remember",
                        "arguments": {
                            "label": "R2",
                            "confirmed": True,
                            "places": [{"name": "mpr", "repo": "Samprand/mpr"}],
                            "chain": ["mpr", "mpr news"],
                        },
                    },
                }
            ]
        )
        assert reply["result"]["content"][0]["text"] == "guardada (hecho): x"
        [(path, body)] = self.sent
        assert path == "/memory/sessions/act" and body["origin_id"] == "s-77"
        assert body["label"] == "R2" and body["confirmed"] is True
        assert body["places"] == [{"name": "mpr", "description": "", "repo": "Samprand/mpr"}]
        assert body["chain"] == ["mpr", "mpr news"]

    def test_remember_without_a_noted_session_says_so_and_sends_nothing(self) -> None:
        [reply] = self.rpc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "remember", "arguments": {"label": "R1", "text": "x"}},
                }
            ],
            cwd="/elsewhere",
        )
        assert reply["result"]["content"][0]["text"] == mcp.NO_SESSION and self.sent == []

    def test_search_and_report_reach_their_paths(self) -> None:
        _client.note_session("/work/relebo", "s-77")
        self.rpc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "search_memories", "arguments": {"query": "mpr"}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "report_memory_issue",
                        "arguments": {"text": "kept twice", "memory_ids": [5]},
                    },
                },
            ]
        )
        assert [p for p, _ in self.sent] == ["/memory/search", "/memory/sessions/feedback"]
        assert self.sent[0][1]["query"] == "mpr" and self.sent[1][1]["memory_ids"] == [5]

    def test_the_engines_work_tools_are_listed_beside_the_memorys(self) -> None:
        schema = {"type": "object", "properties": {"workspace_id": {"type": "integer"}}}
        self.work_tools = _client.Reply(
            200,
            {"tools": [{"name": "list_workflows", "description": "d", "input_schema": schema}]},
        )
        [listed] = self.rpc([{"jsonrpc": "2.0", "id": 8, "method": "tools/list"}])
        assert listed["result"]["tools"][3] == {
            "name": "list_workflows",
            "description": "d",
            "inputSchema": schema,
        }

    def test_a_work_tool_is_carried_to_the_engine_and_answers_its_json(self) -> None:
        _client.post_reply = lambda path, body, timeout=0: (
            self.sent.append((path, body)) or _client.Reply(200, {"run_id": 9})
        )
        [reply] = self.rpc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "start_workflow",
                        "arguments": {"workspace_id": 2, "key": "seo"},
                    },
                }
            ]
        )
        assert self.sent == [
            ("/work/tools/start_workflow", {"arguments": {"workspace_id": 2, "key": "seo"}})
        ]
        assert json.loads(reply["result"]["content"][0]["text"]) == {"run_id": 9}

    def test_a_token_of_the_memory_alone_is_told_to_sign_in_again(self) -> None:
        refused = {"detail": {"code": "scope_missing", "message": "no", "scope": "work"}}
        _client.post_reply = lambda path, body, timeout=0: _client.Reply(403, refused)
        [reply] = self.rpc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "list_workspaces", "arguments": {}},
                }
            ]
        )
        assert "/relebo:login" in reply["result"]["content"][0]["text"]

    def test_an_unknown_method_is_an_error_and_a_notification_is_silent(self) -> None:
        [reply] = self.rpc(
            [
                {"jsonrpc": "2.0", "method": "notifications/cancelled"},
                {"jsonrpc": "2.0", "id": 7, "method": "resources/list"},
            ]
        )
        assert reply["error"]["code"] == -32601


if __name__ == "__main__":
    unittest.main()
