"""The place and the doing as the machine shows them: the git root, its remote and the
folder's name; a file's path inside the project; the lines an edit is about to write and the
lines a turn changed. Hard signals only, read here because only this machine can."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})


def _git(cwd: str, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", cwd or ".", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def root_of(cwd: str) -> Path:
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if top:
        return Path(top)
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or ".").resolve()


def remote_of(cwd: str) -> str:
    return _git(cwd, "remote", "get-url", "origin")


def folder_of(cwd: str) -> str:
    return root_of(cwd).name


def relative(cwd: str, file_path: str):
    if not file_path:
        return None
    try:
        return str(Path(file_path).resolve().relative_to(root_of(cwd).resolve()))
    except ValueError:
        return None


def action_of(payload: dict) -> dict:
    """What a tool hook tells the memory about the action, as the engine's request wants it."""
    cwd = payload.get("cwd", "")
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    action = {
        "origin_id": str(payload.get("session_id") or ""),
        "tool": tool,
        "root": str(root_of(cwd)),
    }
    if tool == "Bash":
        action["command"] = str(tool_input.get("command") or "")
        return action
    file_path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    action["path"] = relative(cwd, file_path)
    if tool in EDIT_TOOLS:
        action["written"] = written(tool_input)
    return action


def written(tool_input: dict) -> list:
    """The lines an edit tool is about to write, as given to it."""
    parts = [str(tool_input.get(key) or "") for key in ("new_string", "content", "new_source")]
    parts += [str(edit.get("new_string") or "") for edit in tool_input.get("edits") or []]
    return [line for line in "\n".join(parts).splitlines() if line.strip()]


def changed_lines(root: Path, path: str) -> list:
    """What a turn changed in a file, from git: the review judges the turn, not the file's past."""
    try:
        content = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    whole = [line for line in content.splitlines() if line.strip()]
    if not _git(str(root), "ls-files", "--error-unmatch", path):
        # a file the turn created: all of it is the turn's doing
        return whole
    diff = _git(str(root), "diff", "-U0", "HEAD", "--", path)
    return [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++") and line[1:].strip()
    ]
