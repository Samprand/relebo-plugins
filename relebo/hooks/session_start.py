"""SessionStart: register the session as a run and inject what the session needs to
work on this project — which project it is, the coding rules (personal rubric, then
each shared one) and the project facts, personal and shared. On compact the same
injection repeats, so long sessions never go blind. The turn snapshot taken here is
what the gate diffs the first turn against."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402
import _git  # noqa: E402


def _git_remote(cwd: str) -> str:
    return _git.run(cwd, "remote", "get-url", "origin").strip() if cwd else ""


_RENDER_RUBRIC = "rubric"


def _context(renders: list[dict], stale: bool, mode: str, project: str | None) -> str:
    present = [
        f"{'rubric' if (r.get('kind') or _RENDER_RUBRIC) == _RENDER_RUBRIC else 'facts'} {r['scope']}"
        for r in renders
        if r.get("content")
    ]
    header = (
        f"[Relebo session — project: {project or 'unregistered'} · gate {mode} · "
        f"loaded: {', '.join(present) or 'nothing'}"
        f"{' · STALE — engine unreachable' if stale else ''}]"
    )
    blocks = [header]
    for render in renders:
        if not render.get("content"):
            continue
        kind = render.get("kind") or _RENDER_RUBRIC
        label = "rubric" if kind == _RENDER_RUBRIC else "project facts"
        blocks.append(f"[Relebo {label} — {render['scope']} · v{render['version']}]\n{render['content']}")
    return "\n\n".join(blocks)


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    claude_session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", "")
    source = payload.get("source", "startup")
    mode = _client.gate_mode()

    session = _client.post(
        "/machine/sessions",
        {
            "claude_session_id": claude_session_id,
            "cwd": cwd,
            "git_remote": _git_remote(cwd),
            "source": source,
            "gate_mode": mode,
        },
    )

    if session is not None:
        _client.save_session(claude_session_id, session["run_id"], mode)
        _client.save_turn_base(claude_session_id, _git.snapshot(cwd))
        _client.cache_renders(session["renders"])
        _client.flush_spool(claude_session_id, session["run_id"])
        _client.close_orphans(claude_session_id)
        context = _context(session["renders"], stale=False, mode=mode, project=session.get("project"))
    else:
        _client.save_turn_base(claude_session_id, _git.snapshot(cwd))
        context = _context(_client.cached_renders(), stale=True, mode=mode, project=None)

    if context:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A hook must never brick a session.
        pass
