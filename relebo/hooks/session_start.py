"""SessionStart: register the session as a run and inject the pinned renders —
the personal rubric first, then each shared one. On compact the same injection
repeats, so long sessions never go blind. In shadow mode the personal render is
cached but not injected: the rubric it mirrors is already in context."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402


def _git_remote(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


_RENDER_RUBRIC = "rubric"


def _context(renders: list[dict], stale: bool, mode: str) -> str:
    blocks = []
    for render in renders:
        if not render.get("content"):
            continue
        kind = render.get("kind") or _RENDER_RUBRIC
        if mode == _client.SHADOW and render.get("scope") == "personal" and kind == _RENDER_RUBRIC:
            continue
        label = "rubric" if kind == _RENDER_RUBRIC else "project facts"
        marker = " · STALE render — engine unreachable" if stale else ""
        blocks.append(
            f"[Relebo {label} — {render['scope']} · v{render['version']}{marker}]\n"
            f"{render['content']}"
        )
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
        _client.cache_renders(session["renders"])
        _client.flush_spool(claude_session_id, session["run_id"])
        _client.close_orphans(claude_session_id)
        context = _context(session["renders"], stale=False, mode=mode)
    else:
        context = _context(_client.cached_renders(), stale=True, mode=mode)

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
