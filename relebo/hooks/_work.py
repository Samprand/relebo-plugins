"""The person's work in Relebo, from the agent's hand: their workspaces, the workflows of
each, starting one, a one-off plan and the run that follows. The tools are the engine's own
(GET /work/tools): this device keeps no copy of them, so a tool the engine gains is offered
here the next session. Claude Code reaches them through mcp.py, Codex through work.py."""

import json

import _client

TOOLS_PATH = "/work/tools"
# the cause the engine gives a token that was issued for the memory alone
SCOPE_MISSING = "scope_missing"

NOT_CONNECTED = "this device is not connected to Relebo"
NOT_REACHED = "Relebo's engine did not answer; nothing was done"
ENGINE_SAID = "the engine answered %s; nothing was done"
SIGN_IN_AGAIN = (
    "this device signed in to Relebo before its work tools existed, so it reaches the memory "
    "only. Tell the person to sign it out and in again (/relebo:logout, then /relebo:login): "
    "the new sign-in carries the work tools"
)


def tools() -> list:
    """The work tools the engine offers this device; none when it is not connected, the
    engine is not reached or the token does not carry them."""
    if not _client.identified():
        return []
    reply = _client.get_reply(TOOLS_PATH, timeout=_client.LOGIN_TIMEOUT_S)
    listed = (reply.body or {}).get("tools") if reply.ok else None
    return [tool for tool in listed or [] if isinstance(tool, dict) and tool.get("name")]


def call(name: str, arguments: dict) -> str:
    """One work tool carried to the engine: its answer as JSON, or why there is none."""
    if not _client.identified():
        return NOT_CONNECTED
    reply = _client.post_reply(
        TOOLS_PATH + "/" + name, {"arguments": arguments}, timeout=_client.TIMEOUT_S
    )
    if reply.ok:
        return json.dumps(reply.body, ensure_ascii=False)
    _client.log("work " + name + " refused: " + str(reply.status) + " " + reply.error_code)
    if reply.status == 0:
        return NOT_REACHED
    if reply.error_code == SCOPE_MISSING:
        return SIGN_IN_AGAIN
    return ENGINE_SAID % reply.status
