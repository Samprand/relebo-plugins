"""The place and the doing as the machine shows them: the git root, its remote and the
folder's name; a file's path inside the project; the lines an edit is about to write and the
lines a turn changed. Hard signals only, read here because only this machine can."""

from __future__ import annotations

import os
import re
import shlex
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
# a word of a command that names a thing to read, not a word to look for: a path, a file
# with its extension, a dotfile, or a variable of the environment
_FILE_LIKE = re.compile(r"(/|^[.~$]|\.[A-Za-z0-9]{1,8}$)")
_QUOTED = re.compile(r"\"(?:[^\"\\\\]|\\\\.)*\"|'[^']*'")


def read_only(command: str) -> bool:
    """Whether a shell command only looks at the project: every program in it is one that
    reads, nothing is redirected or piped into a writer, and nothing it names could leak.
    What sits inside quotes is a word to look for, not a program, a pipe or a file: on
    2026-10-15 `grep "a\\|b" file` was split at its bar and asked about, and a grep for the
    word "token" was taken for a read of one."""
    text = command.strip()
    if not text or _WRITES.search(_bare(text)):
        return False
    for part in _commands(text):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        while words and (words[0] in ("cd",) or "=" in words[0] and not words[0].startswith("-")):
            words = words[2:] if words[0] == "cd" else words[1:]
        if not words:
            continue
        program = words[0].rsplit("/", 1)[-1]
        if program not in _READ_PROGRAMS:
            return False
        if program == "git" and (len(words) < 2 or words[1] not in _READ_GIT):
            return False
        if any(_SECRETS.search(w) and _FILE_LIKE.search(w) for w in words[1:]):
            return False
    return True


def _bare(text: str) -> str:
    """The command with what sits inside quotes blanked: the shell's own words remain."""
    return _QUOTED.sub(lambda found: '"' + " " * (len(found.group(0)) - 2) + '"', text)


def _commands(text: str) -> list:
    """The simple commands of a line, split at &&, ||, ; and | that stand outside quotes."""
    parts, start, quote, i = [], 0, "", 0
    while i < len(text):
        char = text[i]
        if quote:
            if char == "\\" and quote == '"':
                i += 1
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "\\":
            i += 1
        elif text.startswith(("&&", "||"), i):
            parts.append(text[start:i])
            i += 1
            start = i + 1
        elif char in ";|":
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


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
        # what the command does and for what, as the agent told its harness: the first
        # sentence the person reads when the action is theirs to decide
        "description": str(tool_input.get("description") or "")[:600],
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
# what says what a place is, read by the machine for the memory: the README and the manifests.
# Never CLAUDE.md or AGENTS.md, a client's internal instructions, and never the commits'
# e-mail domains (Julián, 2026-10-14)
_ABOUT_FILES = ("README.md", "README", "readme.md", "README.rst")
_ABOUT_MANIFESTS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Package.swift", "pubspec.yaml")
_ABOUT_HEAD_CHARS = 6000
_ABOUT_MANIFEST_CHARS = 800
_ABOUT_MAX_CHARS = 12000


def _scrubbed(text: str) -> str:
    """The text without the lines that look like a secret or a credential: a README or a
    CLAUDE.md sometimes carries a token or a connection string."""
    return "\n".join(
        line for line in text.splitlines() if not (_SECRETS.search(line) and ("=" in line or ":" in line))
    )


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
            parts.append(f"## {name}\n{_scrubbed(head).strip()}")
            if name.upper().startswith("README"):
                break
    for name in _ABOUT_MANIFESTS:
        path = root / name
        if path.is_file():
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:_ABOUT_MANIFEST_CHARS]
            except OSError:
                continue
            parts.append(f"## {name}\n{_scrubbed(head).strip()}")
    folders = [n for n in entries if (root / n).is_dir()]
    if folders:
        parts.append("## top-level folders\n" + ", ".join(folders[:40]))
    return "\n\n".join(parts)[:_ABOUT_MAX_CHARS]


_SIGNAL_COMMITS = 50
_SIGNAL_SIBLINGS = 20


def signals_of(root: Path) -> str:
    """The surroundings of a place, as evidence beside its files, all of it public or
    structural: the remote's host and path (the owner and the groups), the copyright holder
    of its LICENSE, the fields of its manifests that name an organisation (the scope of a
    package name, the homepage, the repository, the keywords, a bundle id), the ticket
    prefixes in its branch names, its parent folder and how many repositories stand beside
    it. No one of them decides; together they justify."""
    lines: list[str] = []
    remote = _git(str(root), "remote", "get-url", "origin")
    if remote:
        bare = re.sub(r"^[a-z+]+://", "", remote).split("@")[-1].replace(":", "/", 1)
        host, _, path = bare.partition("/")
        lines.append(f"remote host: {host.split(':')[0]}")
        groups = [g for g in path.split("/") if g][:-1]
        if groups:
            lines.append("remote owner and groups: " + "/".join(groups))
    holder = _copyright_of(root)
    if holder:
        lines.append(f"LICENSE copyright: {holder}")
    for line in _manifest_facts(root):
        lines.append(line)
    prefixes = _ticket_prefixes(root)
    if prefixes:
        lines.append("ticket prefixes in branch names: " + ", ".join(prefixes))
    parent = root.resolve().parent
    lines.append(f"parent folder: {parent.name}")
    try:
        siblings = [
            p.name
            for p in parent.iterdir()
            if p.is_dir() and p.name != root.name and not p.name.startswith(".") and (p / ".git").exists()
        ]
    except OSError:
        siblings = []
    if siblings:
        # how many, never which: the projects beside it may be other clients' and stay here
        lines.append(f"repositories beside it: {len(siblings)}")
    return "\n".join(lines)


_COPYRIGHT = re.compile(r"(?im)^.*copyright\s*(?:\(c\)|©)?\s*[0-9,\- ]*\s*(.+?)\s*$")
_TICKET = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,9})-[0-9]+")
_MANIFEST_KEYS = ("name", "description", "homepage", "repository", "keywords", "author", "organization")


def _copyright_of(root: Path) -> str:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "NOTICE"):
        path = root / name
        if not path.is_file():
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        found = _COPYRIGHT.search(head)
        if found:
            holder = found.group(1).strip().strip(".")
            return holder[:120]
    return ""


def _manifest_facts(root: Path) -> list[str]:
    """The fields of the manifests that name an organisation or a product, read as plain
    text: the scope of a package name, the homepage, the repository, the keywords, a bundle
    id. Values only, no secrets live in these fields."""
    facts: list[str] = []
    package = root / "package.json"
    if package.is_file():
        try:
            import json as _json

            data = _json.loads(package.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict):
            for key in _MANIFEST_KEYS:
                value = data.get(key)
                if isinstance(value, dict):
                    value = value.get("url") or value.get("name")
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value[:8])
                if value:
                    facts.append(f"package.json {key}: {str(value)[:160]}")
    pubspec = root / "pubspec.yaml"
    if pubspec.is_file():
        try:
            text = pubspec.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            text = ""
        for key in ("name", "description", "homepage", "repository"):
            found = re.search(rf"(?m)^{key}:\s*(.+)$", text)
            if found:
                facts.append(f"pubspec {key}: {found.group(1).strip()[:160]}")
    for gradle in (root / "android" / "app" / "build.gradle", root / "android" / "app" / "build.gradle.kts"):
        if gradle.is_file():
            try:
                found = re.search(r'applicationId\s*=?\s*["\']([^"\']+)["\']', gradle.read_text(encoding="utf-8", errors="replace")[:20000])
            except OSError:
                found = None
            if found:
                facts.append(f"android applicationId: {found.group(1)}")
            break
    return facts[:10]


def _ticket_prefixes(root: Path) -> list[str]:
    """The ticket prefixes the branch names carry (WEB-851 gives WEB): which tracker project
    the work of this repository is filed under. Only the prefixes, never the titles."""
    names = _git(str(root), "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes")
    counts: dict[str, int] = {}
    for prefix in _TICKET.findall(names or ""):
        counts[prefix] = counts.get(prefix, 0) + 1
    return [p for p, _ in sorted(counts.items(), key=lambda c: -c[1])[:4]]



_COMMAND_PATHS_MAX = 12
_COMMAND_PATH = re.compile(r"(?:^|[\s;&|(])(?:cd\s+|-C\s+)?(\"[^\"]+\"|'[^']+'|[~./A-Za-z0-9_][^\s;&|)]*)")


def repo_in_command(cwd: str, command: str):
    """The repository a shell command goes into, other than the session's own: the first
    word of it that is a folder or file inside a git repository whose root is not the
    session's. None when it names none."""
    own = _git(cwd, "rev-parse", "--show-toplevel")
    base = Path(cwd or ".")
    looked = 0
    for raw in _COMMAND_PATH.findall(command or ""):
        word = raw.strip("\"'")
        if not word or word.startswith("-") or "=" in word or word.startswith(_PROGRAM_ROOTS):
            continue
        # a word that could be a path: a slash, a dot, a tilde, or a folder of this place;
        # one longer than any file name (a commit message in the command) is none
        try:
            if not ("/" in word or word.startswith((".", "~")) or (base / word).is_dir()):
                continue
        except OSError:
            continue
        looked += 1
        if looked > _COMMAND_PATHS_MAX:
            break
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


def locale_of() -> str:
    """The machine's locale, as a hint of the person's language: weak (a machine set to
    en_US by a person who writes Spanish), so the engine lets their words win."""
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value and not value.startswith(("C", "POSIX")):
            return value[:40]
    try:
        import locale as _locale

        return (_locale.getlocale()[0] or "")[:40]
    except (ValueError, TypeError):
        return ""


def time_zone_of() -> str:
    """The machine's time zone by its IANA name (America/Bogota), from the system's link
    when it has one; else the abbreviation the clock gives."""
    for link in ("/etc/localtime",):
        try:
            target = os.readlink(link)
        except OSError:
            continue
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1][:80]
    try:
        import time as _time

        return (_time.tzname[0] or "")[:80]
    except (IndexError, AttributeError):
        return ""
