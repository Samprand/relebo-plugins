"""The place and the doing as the machine shows them: the git root, its remote and the
folder's name; a file's path inside the project; the lines an edit is about to write and the
lines a turn changed. Hard signals only, read here because only this machine can."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
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


# what makes a folder a project when it is no repository: something that says what it builds
_MANIFESTS = (
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "Package.swift",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "composer.json",
    "CLAUDE.md",
    "AGENTS.md",
)


def in_project(cwd: str) -> bool:
    """Whether the session runs in a project at all: a repository, or a folder with a manifest.
    The person's home or a folder of files is neither."""
    if _git(cwd, "rev-parse", "--show-toplevel"):
        return True
    root = root_of(cwd)
    return any((root / name).exists() for name in _MANIFESTS)


def scratch(file_path: str) -> bool:
    """A file in the system's temporary space is nobody's: not of the project, not of the
    person's machine in any lasting way. Writing one breaks no rule and endangers nothing, so
    the gate is not asked about it."""
    if not file_path:
        return False
    try:
        path = Path(file_path).resolve()
    except OSError:
        return False
    roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve(), Path("/private/tmp").resolve()}
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return str(path).startswith(("/private/var/folders/", "/var/folders/"))


# where a shell command's tools live: a path there is a program, not a thing the command touches
_PROGRAM_ROOTS = ("/usr/", "/bin/", "/sbin/", "/opt/", "/Library/", "/System/", "/dev/", "/etc/", "/proc/")


# a shell command that only looks: when the engine cannot answer in time, one of these goes
# through, since nothing of the place is changed by it; one that reads what must not leak does not
_READ_PROGRAMS = {
    "ls", "cat", "head", "tail", "less", "more", "wc", "grep", "rg", "egrep", "fgrep", "find",
    "fd", "pwd", "echo", "which", "whoami", "date", "env", "printenv", "stat", "file", "du",
    "df", "tree", "diff", "sed", "awk", "sort", "uniq", "cut", "tr", "jq", "basename", "dirname",
    "realpath", "readlink", "type", "md5", "shasum", "git",
}
_READ_GIT = {"status", "log", "diff", "show", "branch", "rev-parse", "remote", "ls-files", "blame", "describe", "tag"}
_WRITES = re.compile(r"(>|>>|\|\s*(tee|xargs)\b|\brm\b|\bmv\b|\bcp\b|\bsed\s+-i\b|\bchmod\b|\bchown\b|\bsudo\b)")
_SECRETS = re.compile(r"(?i)(\.env\b|\.env\.|secret|credential|token|api[_-]?key|\.pem\b|id_rsa|\.npmrc|\.netrc|keychain|password)")


def read_only(command: str) -> bool:
    """Whether a shell command only looks at the project: every program in it is one that
    reads, nothing is redirected or piped into a writer, and nothing it names could leak."""
    text = command.strip()
    if not text or _WRITES.search(text) or _SECRETS.search(text):
        return False
    for part in re.split(r"\s*(?:&&|\|\||;|\|)\s*", text):
        words = part.strip().split()
        while words and (words[0] in ("cd",) or "=" in words[0] and not words[0].startswith("-")):
            words = words[2:] if words[0] == "cd" else words[1:]
        if not words:
            continue
        program = words[0].rsplit("/", 1)[-1]
        if program not in _READ_PROGRAMS:
            return False
        if program == "git" and (len(words) < 2 or words[1] not in _READ_GIT):
            return False
    return True


def scratch_command(command: str) -> bool:
    """A shell command that names only files in the system's temporary space touches nothing
    of the place: the gate is not asked about it either. A command that names no file at
    all, or any file elsewhere, is judged as always."""
    paths = [p for p in re.findall(r"(?<![\w@:])/[A-Za-z0-9_./-]+", command) if not p.startswith(_PROGRAM_ROOTS)]
    return bool(paths) and all(scratch(p) for p in paths)


def relative(cwd: str, file_path: str):
    if not file_path:
        return None
    try:
        return str(Path(file_path).resolve().relative_to(root_of(cwd).resolve()))
    except ValueError:
        return None


def place_of(cwd: str, file_path: str) -> tuple[Path, str]:
    """The repository a file belongs to and its remote: the file's own git root when it has
    one, the session's otherwise. From a folder that holds several repositories (MPR on
    2026-10-12) each file is of its own, whatever folder the session started in."""
    if file_path:
        try:
            where = str(Path(file_path).resolve().parent)
        except OSError:
            where = ""
        top = _git(where, "rev-parse", "--show-toplevel") if where else ""
        if top:
            return Path(top), _git(top, "remote", "get-url", "origin")
    root = root_of(cwd)
    return root, remote_of(cwd)


def action_of(payload: dict) -> dict:
    """What a tool hook tells the memory about the action, as the engine's request wants it:
    the file's path inside its own repository, and that repository's folder and remote."""
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
        # a command that goes into a repository (cd it, git -C it, a path inside it) is of that
        # repository: on 2026-10-12 "what branch is apm ui on" was answered with git from the
        # folder of repositories, and apm-ui was never recognised
        entered = repo_in_command(cwd, action["command"])
        if entered is not None:
            root, remote = entered
            action["root"] = str(root)
            action["folder"] = root.name
            action["remote"] = remote
        return action
    file_path = str(
        tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path") or ""
    )
    root, remote = place_of(cwd, file_path)
    action["root"] = str(root)
    try:
        action["path"] = str(Path(file_path).resolve().relative_to(root.resolve())) if file_path else None
    except ValueError:
        action["path"] = None
    if action["path"] is not None:
        action["folder"] = root.name
        action["remote"] = remote
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


# what says what a place is, read by the machine for the memory to check a base against: the
# agent was not relied on to read it (on 2026-10-12 it did so one time in two)
_ABOUT_FILES = ("README.md", "README", "readme.md", "README.rst", "CLAUDE.md", "AGENTS.md")
_ABOUT_MANIFESTS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Package.swift", "pubspec.yaml")
_ABOUT_HEAD_CHARS = 6000
_ABOUT_MANIFEST_CHARS = 800
_ABOUT_MAX_CHARS = 12000


def about_of(root: Path) -> str:
    """The head of the README (or CLAUDE.md, AGENTS.md), the head of the manifests and the
    top-level folders of a place, as one text; empty when the place has none of them."""
    parts: list[str] = []
    try:
        entries = sorted(p.name for p in root.iterdir() if not p.name.startswith("."))
    except OSError:
        return ""
    for name in _ABOUT_FILES:
        path = root / name
        if path.is_file():
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:_ABOUT_HEAD_CHARS]
            except OSError:
                continue
            parts.append(f"## {name}\n{head.strip()}")
            if name.upper().startswith("README"):
                break
    for name in _ABOUT_MANIFESTS:
        path = root / name
        if path.is_file():
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:_ABOUT_MANIFEST_CHARS]
            except OSError:
                continue
            parts.append(f"## {name}\n{head.strip()}")
    folders = [n for n in entries if (root / n).is_dir()]
    if folders:
        parts.append("## top-level folders\n" + ", ".join(folders[:40]))
    return "\n\n".join(parts)[:_ABOUT_MAX_CHARS]


_SIGNAL_COMMITS = 50
_SIGNAL_SIBLINGS = 20


def signals_of(root: Path) -> str:
    """The surroundings of a place, as evidence beside its files: the remote's host, the
    e-mail domains of its recent commits, its parent folder and the repositories beside it.
    No one of them decides; together they justify."""
    lines: list[str] = []
    remote = _git(str(root), "remote", "get-url", "origin")
    if remote:
        host = re.sub(r"^[a-z+]+://", "", remote).split("@")[-1].split("/")[0].split(":")[0]
        lines.append(f"remote host: {host}")
    log = _git(str(root), "log", f"-{_SIGNAL_COMMITS}", "--format=%ae")
    if log:
        domains: dict[str, int] = {}
        for address in log.splitlines():
            domain = address.strip().split("@")[-1].lower()
            if domain:
                domains[domain] = domains.get(domain, 0) + 1
        top = sorted(domains.items(), key=lambda d: -d[1])[:3]
        lines.append("commit e-mail domains: " + ", ".join(f"{d} ({n})" for d, n in top))
    parent = root.resolve().parent
    lines.append(f"parent folder: {parent.name}")
    try:
        siblings = sorted(
            p.name
            for p in parent.iterdir()
            if p.is_dir() and p.name != root.name and not p.name.startswith(".") and (p / ".git").exists()
        )[:_SIGNAL_SIBLINGS]
    except OSError:
        siblings = []
    if siblings:
        lines.append("repositories beside it: " + ", ".join(siblings))
    return "\n".join(lines)


_COMMAND_PATH = re.compile(r"(?:^|[\s;&|(])(?:cd\s+|-C\s+)?(\"[^\"]+\"|'[^']+'|[~./A-Za-z0-9_][^\s;&|)]*)")


def repo_in_command(cwd: str, command: str):
    """The repository a shell command goes into, other than the session's own: the first
    word of it that is a folder or file inside a git repository whose root is not the
    session's. None when it names none."""
    own = _git(cwd, "rev-parse", "--show-toplevel")
    base = Path(cwd or ".")
    for raw in _COMMAND_PATH.findall(command or ""):
        word = raw.strip("\"'")
        if not word or word.startswith("-") or "=" in word or word.startswith(_PROGRAM_ROOTS):
            continue
        path = Path(word).expanduser()
        if not path.is_absolute():
            path = base / path
        try:
            if not path.exists():
                continue
            where = str(path if path.is_dir() else path.parent)
        except OSError:
            continue
        top = _git(where, "rev-parse", "--show-toplevel")
        if top and top != own:
            return Path(top), _git(top, "remote", "get-url", "origin")
    return None
