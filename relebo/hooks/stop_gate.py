"""Stop: the machine-scope supervisor gates the turn. The delta since the last
gate — assistant text plus a digest of EVERY tool use — goes to the engine
together with the deterministic guard findings. In enforce mode a block returns
the findings to the agent (bounded retries, then the engine escalates to the
inbox and the turn delivers); in shadow mode nothing ever blocks — the verdict
is audited and a one-line receipt says what would have blocked. Engine
unreachable → the guards still gate and the turn carries a visible
unsupervised receipt, never a silent pass."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _client  # noqa: E402
import _git  # noqa: E402
import _guards  # noqa: E402

_CURSOR_DIR = Path.home() / ".relebo" / "sessions"
_MAX_TOOL_CHARS = 400
_MAX_PROMPT_CHARS = 4000
_MAX_RECEIPT_CHARS = 300
_MAX_BLOCKS_PER_TURN = 3
_GATE_TIMEOUT_S = 90
_MAX_FILES = 12
_MAX_FILE_CHARS = 6000
_MAX_TOTAL_FILE_CHARS = 40000
_HEAD_LINES = 200
_SOURCE_EDIT = "edit"
_SOURCE_HISTORY = "history"
_SOURCE_GIT = "git"
_ANCHOR_RE = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)
_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
# Claude Code replays tool/system output as user entries; those never authorize work.
_INJECTED_PREFIXES = (
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<task-notification>",
    "Stop hook feedback:",
    "Base directory for this skill:",
)


def _cursor_path(claude_session_id: str) -> Path:
    return _CURSOR_DIR / f"{claude_session_id}{_client.CURSOR_SUFFIX}"


def _load_cursor(claude_session_id: str, transcript_path: str) -> dict:
    path = _cursor_path(claude_session_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    # No cursor for a transcript with history (a lost file, a plugin update): judging from
    # line 0 would treat the whole session as this turn. The last prompt is where it starts.
    return {"line": _last_prompt_line(transcript_path), "turn_line": 0, "turn_key": "", "blocks": 0}


def _last_prompt_line(transcript_path: str) -> int:
    last = 0
    for index, line in enumerate(Path(transcript_path).read_text().splitlines()):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and _user_text(entry):
            last = index
    return last


def _save_cursor(claude_session_id: str, cursor: dict) -> None:
    _CURSOR_DIR.mkdir(parents=True, exist_ok=True)
    _cursor_path(claude_session_id).write_text(json.dumps(cursor))


def _user_text(entry: dict) -> str:
    if entry.get("type") != "user" or entry.get("isSidechain"):
        return ""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        if any(isinstance(i, dict) and i.get("type") == "tool_result" for i in content):
            return ""
        text = "\n".join(
            i.get("text", "") for i in content if isinstance(i, dict) and i.get("type") == "text"
        )
    else:
        return ""
    text = _SYSTEM_REMINDER_RE.sub("", text).strip()
    return "" if text.startswith(_INJECTED_PREFIXES) else text


def _timestamp(entry: dict) -> float:
    raw = entry.get("timestamp")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _read_delta(transcript_path: str, since_line: int) -> tuple[dict, int]:
    tools: list[dict] = []
    edits: list[dict] = []
    prompts: list[str] = []
    touched: dict[str, str] = {}
    final_text = ""
    turn_start = 0.0
    lines = Path(transcript_path).read_text().splitlines()
    for line in lines[since_line:]:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        stamp = _timestamp(entry)
        if stamp and (not turn_start or stamp < turn_start):
            turn_start = stamp
        prompt = _user_text(entry)
        if prompt:
            prompts.append(prompt)
        result = entry.get("toolUseResult")
        result_path = result.get("filePath") if isinstance(result, dict) else None
        if isinstance(result_path, str) and result_path:
            touched.setdefault(result_path, _SOURCE_EDIT)
        if entry.get("type") == "file-history-delta":
            backup = entry.get("backup") or {}
            parent = backup.get("realParentDir")
            tracking = entry.get("trackingPath") or ""
            if parent and tracking:
                touched.setdefault(os.path.join(parent, os.path.basename(tracking)), _SOURCE_HISTORY)
        message = entry.get("message") or {}
        for item in message.get("content") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use":
                name = item.get("name", "")
                tool_input = item.get("input") or {}
                path = (
                    tool_input.get("file_path")
                    or tool_input.get("notebook_path")
                    or tool_input.get("path")
                    or ""
                )
                tools.append(
                    {"name": name, "path": path, "input": json.dumps(tool_input)[:_MAX_TOOL_CHARS]}
                )
                if name in _guards.EDIT_TOOLS:
                    edits.append({"tool": name, "input": tool_input})
                    if path:
                        touched[path] = _SOURCE_EDIT
            elif item.get("type") == "text" and entry.get("type") == "assistant":
                final_text = item.get("text", "")
    delta = {
        "final_text": final_text,
        "tools": tools,
        "edits": edits,
        "user_prompt": "\n\n".join(prompts)[-_MAX_PROMPT_CHARS:],
        "touched": touched,
        "turn_start": turn_start,
    }
    return delta, len(lines)


def _head(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return "".join(handle.readlines()[:_HEAD_LINES])
    except OSError:
        return ""


def _collect_files(
    touched: dict[str, str], cwd: str, turn_start: float, base: dict
) -> tuple[list[dict], list[str]]:
    """Post-state evidence: every file this turn touched, as a diff against the
    snapshot taken when the turn started (HEAD only when there is none) or the head
    of a new file. Git status adds what subagents edited — their transcripts are not
    ours — filtered by mtime so pre-existing dirt stays out."""
    root = _git.run(cwd, "rev-parse", "--show-toplevel").strip() if cwd else ""
    base_commit = base.get("commit", "") if base.get("root") == root else ""
    paths = dict(touched)
    untracked_set: set[str] = set()
    if root:
        for line in _git.run(root, "status", "--porcelain", "--untracked-files=all").splitlines():
            rel = line[3:].split(" -> ")[-1].strip().strip('"')
            if not rel:
                continue
            absolute = os.path.join(root, rel)
            if line.startswith("??"):
                untracked_set.add(absolute)
            if not turn_start:
                continue
            try:
                if os.path.getmtime(absolute) >= turn_start:
                    paths.setdefault(absolute, _SOURCE_GIT)
            except OSError:
                continue

    files: list[dict] = []
    omitted: list[str] = []
    budget = _MAX_TOTAL_FILE_CHARS
    for path, source in sorted(paths.items()):
        if _guards.EXEMPT_PATH_RE.search(path) or not os.path.isfile(path):
            continue
        if len(files) >= _MAX_FILES:
            omitted.append(path)
            continue
        inside_repo = bool(root) and path.startswith(root + os.sep)
        untracked = path in untracked_set or not inside_repo
        rel = os.path.relpath(path, root) if inside_repo else ""
        # No HEAD yet (fresh repo) → diff against the index instead.
        diff = (
            ""
            if untracked
            else (
                _git.run(root, "diff", base_commit or "HEAD", "--", rel)
                or _git.run(root, "diff", "--", rel)
            )
        )
        body = (diff or _head(path))[:_MAX_FILE_CHARS]
        if len(body) > budget:
            omitted.append(path)
            continue
        budget -= len(body)
        files.append(
            {
                "path": path,
                "source": source,
                "untracked": untracked,
                "diff": body if diff else "",
                "head": "" if diff else body,
            }
        )
    return files, omitted


def _cached_anchors() -> set[str]:
    anchors: set[str] = set()
    for render in _client.cached_renders():
        anchors.update(_ANCHOR_RE.findall(render.get("content") or ""))
    return anchors


def _findings_line(findings: list[dict]) -> str:
    if not findings:
        return ""
    first = findings[0]
    line = f"[{first.get('anchor', '')}] {first.get('evidence', '')}"
    if len(findings) > 1:
        line += f" (+{len(findings) - 1} more)"
    return line[:_MAX_RECEIPT_CHARS]


def _block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))


def _receipt(message: str) -> None:
    print(json.dumps({"systemMessage": message}))


def main(payload: dict) -> None:
    claude_session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")
    if not transcript_path or not Path(transcript_path).exists():
        _receipt("Relebo supervisor — no transcript for this turn: unsupervised turn.")
        return
    run_id = _client.ensure_session(claude_session_id, payload.get("cwd", ""))
    if run_id is None:
        _receipt("Relebo supervisor unreachable — unsupervised turn.")
        return

    cursor = _load_cursor(claude_session_id, transcript_path)
    # A retry after any stop-hook block (ours or another plugin's) is the same turn:
    # re-read from where the turn started so the verdict sees the fix in context.
    retrying = bool(payload.get("stop_hook_active")) and bool(cursor.get("turn_key"))
    since_line = cursor.get("turn_line", cursor["line"]) if retrying else cursor["line"]
    delta, line_count = _read_delta(transcript_path, since_line)
    # Claude Code appends the transcript asynchronously: the file may still end at the
    # previous message when Stop fires. The payload's last_assistant_message is the
    # authoritative final text of this turn.
    last_text = payload.get("last_assistant_message")
    if isinstance(last_text, str) and last_text.strip():
        delta["final_text"] = last_text
    if not delta["tools"] and not delta["final_text"].strip():
        return
    turn_key = cursor["turn_key"] if retrying else f"turn-{int(time.time() * 1000)}"
    blocks = cursor.get("blocks", 0) if retrying else 0

    files, omitted = _collect_files(
        delta["touched"],
        payload.get("cwd", ""),
        delta["turn_start"],
        _client.turn_base(claude_session_id),
    )
    # Files changed by shell commands only show up here (git status), never as edit tools:
    # the guards judge the tree's post-state, not the tool that produced it.
    guard_findings = _guards.run(
        delta, _cached_anchors(), [file["path"] for file in files if file.get("path")]
    )
    verdict = _client.post(
        f"/machine/sessions/{run_id}/gate",
        {
            "turn_key": turn_key,
            "final_text": delta["final_text"],
            "tools": delta["tools"],
            "guard_findings": guard_findings,
            "files": files,
            "omitted": omitted,
        },
        timeout=_GATE_TIMEOUT_S,
    )
    mode = (verdict or {}).get("mode") or _client.session_gate_mode(claude_session_id)
    enforce = mode == _client.ENFORCE

    if verdict is None:
        findings = guard_findings
        blocking = enforce and bool(findings)
        prefix = "Relebo supervisor unreachable — unsupervised turn"
    else:
        findings = verdict.get("findings") or []
        blocking = enforce and verdict.get("decision") == "block"
        prefix = "Relebo supervisor"

    if blocking and blocks + 1 < _MAX_BLOCKS_PER_TURN:
        _save_cursor(
            claude_session_id,
            {"line": cursor["line"], "turn_line": since_line, "turn_key": turn_key, "blocks": blocks + 1},
        )
        reason = (verdict or {}).get("reason") or "; ".join(
            f"[{f['anchor']}] {f['evidence']} Fix: {f['fix']}" for f in findings
        )
        _block(f"{prefix} blocked this turn. Fix the findings before delivering: {reason}")
        return

    _save_cursor(
        claude_session_id,
        {"line": line_count, "turn_line": since_line, "turn_key": turn_key, "blocks": 0},
    )
    # The turn is delivered: the next one starts from the tree as it is now.
    _client.save_turn_base(claude_session_id, _git.snapshot(payload.get("cwd", "")))
    if verdict is None:
        message = prefix + (f"; guards would block: {_findings_line(findings)}" if findings else ".")
        _receipt(message)
    elif verdict.get("escalated"):
        _receipt(f"{prefix}: delivered with unresolved findings — escalated to your Inbox.")
    elif verdict.get("decision") == "block":
        _receipt(f"{prefix} (shadow) would block: {_findings_line(findings)}")
    for proposal in (verdict or {}).get("proposals") or []:
        entry_id = proposal.get("inbox_entry_id")
        _receipt(
            f"{prefix}: rubric proposal #{entry_id} ({proposal.get('title')}) awaits the user — "
            "offer relebo_decide_inbox (Claude Code asks them in its dialog) or the Inbox."
        )


if __name__ == "__main__":
    payload = json.loads(sys.stdin.read() or "{}")
    try:
        main(payload)
    except Exception:
        # A hook must never brick a session — but a cursor left behind re-reads the
        # same poisoned delta every turn and the gate stays dead for the session.
        try:
            transcript_path = payload.get("transcript_path", "")
            if payload.get("session_id") and transcript_path and Path(transcript_path).exists():
                line_count = len(Path(transcript_path).read_text().splitlines())
                _save_cursor(
                    payload["session_id"],
                    {"line": line_count, "turn_line": line_count, "turn_key": "", "blocks": 0},
                )
        except (OSError, ValueError):
            pass
        _receipt("Relebo supervisor failed — unsupervised turn.")
