"""Git helpers shared by the hooks: a working-tree snapshot marks where a turn starts,
so the gate judges only what the turn changed — never earlier turns or another
session's uncommitted work in the same tree."""

import subprocess

_TIMEOUT_S = 10


def run(root: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, text=True, timeout=_TIMEOUT_S, check=False
        )
        return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def snapshot(cwd: str) -> dict:
    """{"root", "commit"} for the repo at cwd, {} outside a repo. `stash create`
    writes a commit of index + working tree without touching either; a clean tree
    yields nothing, and HEAD is then the snapshot."""
    root = run(cwd, "rev-parse", "--show-toplevel").strip() if cwd else ""
    if not root:
        return {}
    commit = run(root, "stash", "create").strip() or run(root, "rev-parse", "HEAD").strip()
    return {"root": root, "commit": commit} if commit else {}
