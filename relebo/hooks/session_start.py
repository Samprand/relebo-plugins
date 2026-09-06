"""SessionStart: register the session as a run and inject what the session needs to
work on this project — which project it is, the coding rules (personal rubric, then
each shared one) and the project facts, personal and shared. On compact the same
injection repeats, so long sessions never go blind. The turn snapshot taken here is
what the gate diffs the first turn against."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402
import _git  # noqa: E402


_RENDER_RUBRIC = "rubric"
_SECTION_RE = re.compile(r"^## \[([^\]]+)\]\n(?:_Applies when:_ (.*))?", re.MULTILINE)


def _index(content: str) -> str:
    """One line per rule: the anchor and when it applies. The full section arrives on the
    prompt that needs it."""
    lines = []
    for anchor, applies_when in _SECTION_RE.findall(content):
        lines.append(f"- {anchor}: {applies_when.strip()}" if applies_when else f"- {anchor}")
    return "\n".join(lines)


def _context(renders: list[dict], stale: bool, mode: str, project: str | None) -> str:
    indexed = _client.rubric_context() == _client.RUBRIC_INDEX
    shown = [
        r
        for r in renders
        if r.get("content") and not (indexed and (r.get("kind") or _RENDER_RUBRIC) != _RENDER_RUBRIC)
    ]
    present = [
        f"{'rubric index' if indexed else 'rubric'} {r['scope']}"
        if (r.get("kind") or _RENDER_RUBRIC) == _RENDER_RUBRIC
        else f"facts {r['scope']}"
        for r in shown
    ]
    header = (
        f"[Relebo session — project: {project or 'unregistered'} · gate {mode} · "
        f"loaded: {', '.join(present) or 'nothing'}"
        f"{' · rules and facts arrive per prompt' if indexed else ''}"
        f"{' · STALE — engine unreachable' if stale else ''}]"
    )
    blocks = [header]
    for render in shown:
        kind = render.get("kind") or _RENDER_RUBRIC
        if kind == _RENDER_RUBRIC and indexed:
            blocks.append(
                f"[Relebo rubric index — {render['scope']} · v{render['version']}]\n"
                f"{_index(render['content'])}"
            )
            continue
        label = "rubric" if kind == _RENDER_RUBRIC else "project facts"
        blocks.append(f"[Relebo {label} — {render['scope']} · v{render['version']}]\n{render['content']}")
    return "\n\n".join(blocks)


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    claude_session_id = payload.get("session_id", "")
    cwd = payload.get("cwd", "")
    source = payload.get("source", "startup")
    mode = _client.gate_mode()

    session = _client.open_session(claude_session_id, cwd, source)
    if session is not None:
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
