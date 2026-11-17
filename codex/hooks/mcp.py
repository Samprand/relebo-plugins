"""Relebo's memory as tools of the session, with no command in sight (2026-11-17): a
local MCP server over stdio, with no dependency beyond Python, that hands the agent
`remember`, `search_memories` and `report_memory_issue` and carries each to the engine with
this device's token. The session the calls belong to is the one the hooks noted for this
folder (user_prompt and session_start write it), so a label of the turn is found.

Claude Code starts it from the plugin's .mcp.json; Codex keeps the scripts (keep.py,
search.py, feedback.py) until its plugins carry MCP servers too.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client

PROTOCOL = "2025-06-18"
SERVER = {"name": "relebo", "version": _client.version()}
NO_SESSION = (
    "no Relebo session is noted for this folder yet: the memory's labels live in the turn "
    "the hooks opened; send one message first"
)
NOT_CONNECTED = "this device is not connected to Relebo"
ENGINE_SAID = "the engine answered %s"

TOOLS = [
    {
        "name": "remember",
        "description": (
            "Your call on a label the memory listed under «what the person's words carry» "
            "(R1, R2…). Keep a signal with text: the memory's own words, complete enough to be "
            "read alone (kind work for a piece of work asked). A rule or a preference comes back "
            "waiting for the person's yes: put it to them with the label and call again with "
            "confirmed when they say yes, or drop when they say no. A question listed there is "
            "answered with confirmed (yes), drop (no) or the person's choice in said. A new "
            "place: confirmed, places (one per place: name, description, repo owner/name) and "
            "chain (names from the biggest down). drop alone leaves a label as nothing to keep. "
            "With no label, text keeps your own words. The answer is what happened, the only "
            "truth about what was kept."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "R1, R2… as listed"},
                "text": {"type": "string"},
                "kind": {"type": "string", "enum": ["work"]},
                "confirmed": {"type": "boolean"},
                "drop": {"type": "boolean"},
                "said": {"type": "string", "description": "the person's choice, in their words"},
                "places": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "repo": {"type": "string", "description": "owner/name"},
                        },
                        "required": ["name"],
                    },
                },
                "chain": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "search_memories",
        "description": (
            "Look through the person's memory by words before saying what Relebo holds or does "
            "not: one line per matching memory, with its number, kind, where it lives and its "
            "words. Use it when the person asks what is kept, when you are about to say that "
            "something is already known or saved, and when the thread above says something was "
            "kept: the thread is not the memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "workspace_id": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "report_memory_issue",
        "description": (
            "Send Relebo's maintainers the detail of something the memory did wrong or "
            "doubtfully: a rule kept as a fact, the same thing kept twice, a yes taken for the "
            "wrong question, words not read, a place born wrong. Say what happened, why it looks "
            "wrong and the ids, and name the memories involved. The person hears from you one "
            "plain line."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "memory_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["text"],
        },
    },
]


def call(name: str, arguments: dict, cwd: str) -> str:
    """One tool call carried to the engine; what comes back is what happened."""
    if not _client.identified():
        return NOT_CONNECTED
    session = _client.session_for(cwd)
    if name == "remember":
        if not session:
            return NO_SESSION
        body = {"origin_id": session}
        for key in ("label", "text", "kind", "said"):
            if arguments.get(key):
                body[key] = str(arguments[key])
        for key in ("confirmed", "drop"):
            if arguments.get(key):
                body[key] = True
        body["places"] = [
            {
                "name": str(p.get("name") or ""),
                "description": str(p.get("description") or ""),
                "repo": str(p.get("repo") or ""),
            }
            for p in arguments.get("places") or []
            if isinstance(p, dict) and str(p.get("name") or "").strip()
        ]
        body["chain"] = [str(c) for c in arguments.get("chain") or []]
        path = "/memory/sessions/act"
    elif name == "search_memories":
        body = {"origin_id": session, "query": str(arguments.get("query") or "")}
        if arguments.get("workspace_id") is not None:
            body["workspace_id"] = int(arguments["workspace_id"])
        path = "/memory/search"
    elif name == "report_memory_issue":
        body = {
            "origin_id": session,
            "text": str(arguments.get("text") or ""),
            "memory_ids": [int(i) for i in arguments.get("memory_ids") or []],
        }
        path = "/memory/sessions/feedback"
    else:
        return "unknown tool: " + name
    reply = _client.post_reply(path, body, timeout=_client.TIMEOUT_S)
    if not reply.ok:
        _client.log("mcp " + name + " refused: " + str(reply.status))
        return ENGINE_SAID % reply.status
    return (reply.body or {}).get("context") or "nothing happened"


def answer(request: dict, cwd: str):
    """The JSON-RPC answer to one request, or None for a notification."""
    method = request.get("method") or ""
    rid = request.get("id")
    if rid is None:
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER,
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params") or {}
        text = call(str(params.get("name") or ""), params.get("arguments") or {}, cwd)
        result = {"content": [{"type": "text", "text": text}], "isError": False}
    elif method == "ping":
        result = {}
    else:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32601, "message": "method not found: " + method},
        }
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def serve(stdin, stdout, cwd: str) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        if not isinstance(request, dict):
            continue
        replied = answer(request, cwd)
        if replied is not None:
            stdout.write(json.dumps(replied) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve(sys.stdin, sys.stdout, os.getcwd())
