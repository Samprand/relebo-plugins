"""A review turn writes nothing of its own: the code under judgment is the diff the user
asked about. Fetched here so the recall, the guards and the Stop gate see it the way they
see the agent's own writes — otherwise a review is judged only on its prose."""

from __future__ import annotations

import os
import re
import subprocess

import _git
import _guards

# A review verb, not just a PR number: "implementa el PR #7" is an edit turn whose own
# writes are what the gate judges.
_REVIEW_VERB_RE = re.compile(r"(?i)(\breview\b|\brevisa\w*\b|code.?review)")
_PR_NUMBER_RE = re.compile(r"(?i)(?:\bPR\b|pull\s+request|/pull/)\s*#?\s*(\d+)")
_BRANCH_RE = re.compile(r"(?i)\b(?:rama|branch)\s+([A-Za-z0-9][A-Za-z0-9._/-]*)")
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
_NEW_FILE_MARKER = "new file mode"
_DEFAULT_BASES = (
    "origin/development",
    "origin/main",
    "origin/master",
    "development",
    "main",
    "master",
)
_TIMEOUT_S = 20
_MAX_DIFF_CHARS = 400_000
KIND_PR = "pr"
KIND_BRANCH = "branch"
KIND_CURRENT = "current"
LABEL_WORKING_TREE = "working tree"


def target(prompt: str) -> dict | None:
    """What the prompt asks to review: a PR, a named branch, or whatever is checked out."""
    if not _REVIEW_VERB_RE.search(prompt):
        return None
    pr = _PR_NUMBER_RE.search(prompt)
    if pr:
        return {"kind": KIND_PR, "ref": pr.group(1)}
    branch = _BRANCH_RE.search(prompt)
    if branch:
        return {"kind": KIND_BRANCH, "ref": branch.group(1)}
    return {"kind": KIND_CURRENT}


def base_of(root: str, ref: str) -> tuple[str, int]:
    """(base branch, commits `ref` has over it). Of the bases that exist, the one the ref
    forked from most recently — origin/HEAD alone said `main` for a branch cut from
    `development` and produced the whole of development as the diff. 0 commits: the ref
    sits on that base."""
    tracked = _git.run(root, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").strip()
    candidates = [c for c in (tracked, *_DEFAULT_BASES) if c and c != ref]
    best: tuple[str, int] = ("", -1)
    for candidate in dict.fromkeys(candidates):
        if not _git.run(root, "rev-parse", "--verify", "--quiet", candidate).strip():
            continue
        count = _git.run(root, "rev-list", "--count", f"{candidate}..{ref}").strip()
        if not count.isdigit():
            continue
        ahead = int(count)
        if best[1] < 0 or ahead < best[1]:
            best = (candidate, ahead)
    return best


def _ref(root: str, name: str) -> str:
    for candidate in (name, f"origin/{name}"):
        if _git.run(root, "rev-parse", "--verify", "--quiet", candidate).strip():
            return candidate
    return ""


def _gh_pr_diff(root: str, number: str) -> str:
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", number],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def fetch_diff(root: str, wanted: dict) -> tuple[str, str]:
    """(diff text, label): the branch forms diff from the merge-base with the default
    branch, never from `main` by assumption."""
    if wanted["kind"] == KIND_PR:
        return _gh_pr_diff(root, wanted["ref"])[:_MAX_DIFF_CHARS], f"PR #{wanted['ref']}"
    if wanted["kind"] == KIND_BRANCH:
        ref = _ref(root, wanted["ref"])
        base, ahead = base_of(root, ref) if ref else ("", -1)
        if not base or ahead <= 0:
            return "", ""
        return _git.run(root, "diff", f"{base}...{ref}")[
            :_MAX_DIFF_CHARS
        ], f"branch {ref} vs {base}"
    head = _git.run(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    base, ahead = base_of(root, "HEAD")
    if base and ahead > 0:
        diff = _git.run(root, "diff", f"{base}...HEAD")
        if diff.strip():
            return diff[:_MAX_DIFF_CHARS], f"branch {head} vs {base}"
    return _git.run(root, "diff", "HEAD")[:_MAX_DIFF_CHARS], LABEL_WORKING_TREE


def split(diff_text: str) -> dict[str, dict]:
    """{path: {"added": lines the diff adds, "new": the file did not exist, "diff": its block}}."""
    files: dict[str, dict] = {}
    current: dict | None = None
    for line in diff_text.splitlines():
        header = _DIFF_HEADER_RE.match(line)
        if header:
            current = files.setdefault(header.group(2), {"added": [], "new": False, "diff": []})
        if current is None:
            continue
        current["diff"].append(line)
        if line.startswith(_NEW_FILE_MARKER):
            current["new"] = True
        elif line.startswith("+") and not line.startswith("+++"):
            current["added"].append(line[1:])
    return {
        path: {
            "added": "\n".join(entry["added"]),
            "new": entry["new"],
            "diff": "\n".join(entry["diff"]),
        }
        for path, entry in files.items()
        if entry["added"]
    }


def as_edits(review: dict) -> list[dict]:
    """The reviewed additions in the shape the code guards read."""
    return [
        {"tool": "Write", "input": {"file_path": path, "content": text}}
        for path, text in review["added"].items()
    ]


def guard_findings(review: dict, anchors: set[str]) -> list[dict]:
    """The deterministic guards over the reviewed diff, before any model reads a line."""
    findings = _guards.code_guards(as_edits(review)) + _guards.principal_definition_guards(
        review["paths"], texts=review["new_texts"]
    )
    return [finding for finding in findings if finding["anchor"] in anchors]


def delta(cwd: str, prompt: str) -> dict | None:
    """The reviewed diff as the engine and the guards consume it: absolute paths, the
    added lines per path, each file's diff block, and the full text of files the diff
    creates (their added lines are the whole file, so the one-definition guard can read
    them without a checkout)."""
    wanted = target(prompt)
    if wanted is None:
        return None
    root = _git.run(cwd, "rev-parse", "--show-toplevel").strip() if cwd else ""
    if not root:
        return None
    diff_text, label = fetch_diff(root, wanted)
    files = split(diff_text)
    if not files:
        return None
    added = {os.path.join(root, path): entry["added"] for path, entry in files.items()}
    diffs = {os.path.join(root, path): entry["diff"] for path, entry in files.items()}
    new_texts = {
        os.path.join(root, path): entry["added"] for path, entry in files.items() if entry["new"]
    }
    return {
        "target": label,
        "paths": sorted(added),
        "added": added,
        "diffs": diffs,
        "new_texts": new_texts,
    }
