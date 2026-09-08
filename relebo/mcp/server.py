"""Relebo MCP server: exposes the Relebo engine to Claude Code.

Auth, in order of preference:
  1. The machine identity written by the Relebo runner (~/.relebo/machine.json) — never expires.
  2. RELEBO_TOKEN env (a session token from the app) — expires ~1h.
RELEBO_ENGINE_URL overrides the engine address (else machine.json, else localhost).
"""

import json
import os
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

_STATE_PATH = Path.home() / ".relebo" / "machine.json"
_SESSIONS_DIR = Path.home() / ".relebo" / "sessions"
_DEFAULT_ENGINE_URL = "http://127.0.0.1:8100"

mcp = MCPServer("relebo")


def _state() -> dict:
    """Read on every call: the server outlives re-registrations of the machine, and a
    URL or fingerprint frozen at import time would point at an engine that is gone."""
    if not _STATE_PATH.exists():
        return {}
    try:
        return json.loads(_STATE_PATH.read_text())
    except ValueError:
        return {}


def _engine_url() -> str:
    return (
        os.environ.get("RELEBO_ENGINE_URL") or _state().get("engine_url") or _DEFAULT_ENGINE_URL
    ).rstrip("/")


def _headers() -> dict:
    machine_key = _state().get("fingerprint", "")
    if machine_key:
        return {"X-Machine-Key": machine_key}
    token = os.environ.get("RELEBO_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _request(method: str, path: str, body: dict | None = None) -> object:
    headers = _headers()
    if not headers:
        return {
            "error": (
                "no Relebo identity — enroll this machine with the Relebo runner, or set "
                "RELEBO_TOKEN with a session token from the app"
            )
        }
    url = f"{_engine_url()}{path}"
    try:
        response = httpx.request(method, url, json=body, headers=headers, timeout=120)
    except httpx.HTTPError as e:
        # A readable tool result, never an exception the client shows as "Error executing tool".
        return {"error": f"Relebo engine unreachable at {url}: {e}"}
    if response.status_code >= 400:
        return {"error": f"{response.status_code}: {response.text[:300]}"}
    return response.json()


@mcp.tool()
def relebo_workspaces() -> object:
    """List the workspaces of the current Relebo user (personal first)."""
    return _request("GET", "/workspaces")


@mcp.tool()
def relebo_workflows(workspace_id: int) -> object:
    """List the workflows available in a workspace."""
    return _request("GET", f"/workspaces/{workspace_id}/workflows")


@mcp.tool()
def relebo_trigger_workflow(workspace_id: int, workflow_key: str) -> object:
    """Trigger a workflow run in a workspace and return the run state."""
    return _request(
        "POST", f"/workspaces/{workspace_id}/runs", {"workflow_key": workflow_key}
    )


@mcp.tool()
def relebo_inbox(workspace_id: int) -> object:
    """List the user's Relebo inbox for a workspace (approvals, tasks, escalations)."""
    return _request("GET", f"/workspaces/{workspace_id}/inbox")


@mcp.tool()
def relebo_decide_inbox(entry_id: int, decision: str) -> object:
    """Put a pending Relebo approval or rubric proposal in front of the user: Claude Code
    shows its permission dialog and the user's click there is the decision. decision:
    'approve' or 'reject'. Never call it for a decision the user did not ask you to relay."""
    return _request("POST", f"/machine/approvals/{entry_id}/answer", {"decision": decision})


@mcp.tool()
def relebo_knowledge_subjects(workspace_id: int) -> object:
    """List the knowledge subjects of a workspace."""
    return _request("GET", f"/workspaces/{workspace_id}/subjects")


@mcp.tool()
def relebo_knowledge_pieces(
    subject_id: int, level: int | None = None, page_index: int = 0, page_size: int = 20
) -> object:
    """List the knowledge pieces stored under a subject, one page at a time.
    level: 3 rules, 2 docs, 1 facts, 0 notes; omit for all."""
    query = f"?page_index={page_index}&page_size={page_size}"
    if level is not None:
        query += f"&level={level}"
    return _request("GET", f"/subjects/{subject_id}/pieces{query}")


@mcp.tool()
def relebo_save_knowledge(workspace_id: int, subject: str, content: str, kind: str) -> object:
    """Save a knowledge piece in a workspace. kind: 'atom' (short fact), 'doc' or 'record'."""
    return _request(
        "POST",
        f"/workspaces/{workspace_id}/knowledge",
        {"subject": subject, "content": content, "kind": kind},
    )


@mcp.tool()
def relebo_pause_capture() -> object:
    """Stop Relebo from saving knowledge out of the current Claude Code session — call it
    the moment the user says this session must not be kept (a test, a throwaway client
    integration). Irreversible for the session; earlier captures stay."""
    sessions = sorted(
        (
            path
            for path in _SESSIONS_DIR.glob("*.json")
            if not path.name.endswith(".cursor.json")
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if not sessions:
        return {"error": "no Relebo session on this machine — is the relebo plugin active?"}
    # The prompt hook touched the current session's file an instant ago: newest wins.
    current = sessions[-1]
    run_id = json.loads(current.read_text()).get("run_id")
    if run_id is None:
        return {"error": "the current session has no engine run — capture was never on"}
    result = _request("POST", f"/machine/sessions/{run_id}/capture/pause", {})
    return {"run_id": run_id, "paused": True, "engine": result}


@mcp.tool()
def relebo_recall(query: str) -> object:
    """Pull the coding rules and project facts that a piece of work calls for — call it
    before touching an area of the project you have not read rules or facts about in
    this session. query: what you are about to do, in plain words."""
    sessions = sorted(
        (p for p in _SESSIONS_DIR.glob("*.json") if not p.name.endswith(".cursor.json")),
        key=lambda p: p.stat().st_mtime,
    )
    if not sessions:
        return {"error": "no Relebo session on this machine — is the relebo plugin active?"}
    run_id = json.loads(sessions[-1].read_text()).get("run_id")
    if run_id is None:
        return {"error": "the current session has no engine run"}
    return _request("POST", f"/machine/sessions/{run_id}/recall", {"query": query, "prompt": query})


if __name__ == "__main__":
    mcp.run()
