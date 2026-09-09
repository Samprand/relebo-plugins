"""Deterministic guards: the local layer of the machine-scope supervisor. They
gate mechanically checkable rules with zero judge cost and keep gating when the
engine is unreachable. Findings cite anchors only — a guard whose anchor is not
in the cached renders is dropped, so offline verdicts stay within the pinned
vocabulary. Ported from the previous compliance gate (same author, measured on
~2,600 turns). Stdlib only, python3.9-compatible."""

from __future__ import annotations

import os
import re

ANCHOR_IMPORTS = "imports"
ANCHOR_ONE_PRINCIPAL = "one-principal-definition-per"
ANCHOR_NAMING = "naming-conventions"
ANCHOR_UTILS = "utils-structure"
ANCHOR_REVIEW_STRUCTURE = "review-comment-structure"
ANCHOR_KNOWLEDGE_CAPTURE = "knowledge-capture-corrections-become"

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

EXEMPT_PATH_RE = re.compile(r"/(tmp|scratchpad|\.claude)/")
DART_ENUM_RE = re.compile(r"^\s*enum\s+([A-Za-z_]\w*)\b", re.M)
# Column-0 declaration: return type + lowercase name + paren.
DART_TOPLEVEL_FN_RE = re.compile(
    r"^(?:Future<[^\n]*?>|Stream<[^\n]*?>|List<[^\n]*?>|Map<[^\n]*?>|Set<[^\n]*?>"
    r"|Iterable<[^\n]*?>|void|int|double|num|bool|String|dynamic"
    r"|[A-Z]\w*(?:<[^\n]*?>)?)\??\s+([a-z_]\w*)\s*\(",
    re.M,
)
# Column-0 def is top-level by construction (nested defs are indented).
PY_TOPLEVEL_FN_RE = re.compile(r"^(?:async\s+)?def\s+([a-z_]\w*)\s*\(", re.M)
# Function declarations only — typed const arrows false-positive too easily.
TS_TOPLEVEL_FN_RE = re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$]\w*)", re.M)
UTILS_FN_RES = {
    ".dart": DART_TOPLEVEL_FN_RE,
    ".py": PY_TOPLEVEL_FN_RE,
    ".ts": TS_TOPLEVEL_FN_RE,
    ".tsx": TS_TOPLEVEL_FN_RE,
    ".js": TS_TOPLEVEL_FN_RE,
    ".mjs": TS_TOPLEVEL_FN_RE,
}
# Rubric exemption: test paths mirroring utils/ don't make a file a util.
UTILS_EXEMPT_FILE_RE = re.compile(
    r"(_test\.dart|/test_[^/]*\.py|_test\.py|/conftest\.py|\.test\.[jt]sx?|\.spec\.[jt]sx?)$"
)
# Scoped to `../` only — same-directory `./` is common and low-risk.
RELATIVE_IMPORT_RES = {
    ".dart": re.compile(r"""^\s*import\s+['"]\.\./""", re.M),
    ".ts": re.compile(r"""^\s*(?:import|export)\b[^\n]*?from\s+['"]\.\./""", re.M),
}
for _ext in (".tsx", ".js", ".jsx", ".mjs"):
    RELATIVE_IMPORT_RES[_ext] = RELATIVE_IMPORT_RES[".ts"]
# Only the final file shows how many definitions actually ended up in it.
DECLARATION_DIR_RE = re.compile(r"/(types|enums|dtos|constants)/")
# Column-0 class in a declaration folder: one per file, like a TS export.
PY_TOPLEVEL_CLASS_RE = re.compile(r"^class\s+([A-Za-z_]\w*)\b", re.M)
TS_EXPORT_DECL_RE = re.compile(
    r"^export\s+(?:default\s+)?(?:abstract\s+)?(?:interface|type|class|enum)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
SUPPORTING_TYPE_SUFFIXES = ("Props", "Args", "Params", "Options", "Config")
MAX_GUARD_FILE_BYTES = 200_000

BOLD_TITLE_RE = re.compile(r"^\*\*([^*\n]{3,})\*\*.{0,40}$")
# Verdict-grade markers only — bare "finding"/"review" matched progress summaries.
REVIEW_MARKERS_RE = re.compile(r"(?i)(mergeable|severity\s*:|verdict)")
REVIEW_REQUEST_RE = re.compile(r"(?i)(\breview\b|\brevisa\w*\b|code.?review|\bPR\s*#?\d+\b)")
FIX_LINE_RE = re.compile(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?fix\b")
# Bold lines that are structural labels inside a finding, not finding titles.
LABEL_WORDS = {
    "fix", "description", "title", "scenario", "impact", "guard", "why",
    "what", "where", "learned", "rationale", "change", "target", "assumption",
    "alternative", "option",
}
KNOWLEDGE_TRIGGER_PHRASES = (
    "cuando digo", "cuando me refiero", "siempre haz", "prefiero que",
    "acuerdate que", "acuérdate que", "nunca hagas", "de ahora en adelante",
    "en este proyecto usamos",
)
RUBRIC_ADDITION_MARKER = "rubric addition"

# Effect classes of a shell subcommand, strongest first. Destructive never runs from a
# session; remote and shared-repo effects go to the engine's action gate before running.
EFFECT_DESTRUCTIVE = "destructive"
EFFECT_REMOTE = "remote"
EFFECT_SHARED_REPO = "shared-repo"
EFFECT_KNOWLEDGE_BYPASS = "knowledge-bypass"
SUBCOMMAND_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
ENV_PREFIX_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+")
SUDO_PREFIX_RE = re.compile(r"^sudo\s+(?:-\S+\s+)*")
RM_RECURSIVE_RE = re.compile(r"^rm\s+(?:-\S*r\S*|--recursive)\b")
RM_SAFE_PATH_RE = re.compile(r"^(?:/private)?/tmp/|scratchpad|node_modules|/target(?:/|$)|/dist(?:/|$)|\.venv")
DESTRUCTIVE_RES = (
    re.compile(r"^git\s+push\b.*\s(?:--force|-f|--force-with-lease)\b"),
    re.compile(r"^git\s+push\b.*\s\+\S"),
    re.compile(r"^git\s+(?:reset\s+--hard|clean\s+-\S*f|branch\s+-D|checkout\s+--\s+\.|restore\s+\.)"),
    re.compile(r"^gh\s+repo\s+(?:delete|archive)\b"),
    re.compile(r"^gcloud\s+.*\bdelete\b"),
    re.compile(r"^(?:npx\s+(?:--\S+\s+)*)?supabase\s+db\s+reset\b"),
    re.compile(r"\bdrop\s+(?:table|database|schema)\b", re.I),
)
REMOTE_RES = (
    re.compile(r"^git\s+push\b"),
    re.compile(r"^gh\s+(?:workflow\s+run|release|secret|pr\s+merge|repo\s+(?:create|edit))\b"),
    re.compile(r"^gh\s+api\b.*(?:-X|--method)\s*(?:POST|PUT|PATCH|DELETE)\b"),
    re.compile(r"^gcloud\s+(?:run|secrets|iam|sql|compute|functions|projects)\b"),
    re.compile(r"^(?:npx\s+(?:--\S+\s+)*)?supabase\s+(?:db\s+push|secrets|functions\s+deploy|link)\b"),
    re.compile(r"^(?:npm|pnpm|yarn)\s+publish\b"),
    re.compile(r"^docker\s+push\b"),
    re.compile(r"^(?:kubectl\s+(?:apply|delete|scale)|terraform\s+(?:apply|destroy))\b"),
    re.compile(r"^(?:curl|http|wget)\b.*(?:-X\s*(?:POST|PUT|PATCH|DELETE)\b|--data\b|\s-d\s)"),
)
SHARED_REPO_RES = (re.compile(r"^git\s+(?:commit|merge|rebase|tag|cherry-pick|revert)\b"),)
# Rules and approvals reach Relebo only through the Inbox. Seeding scripts, direct writes to
# the memory or inbox tables and the memory service's adopt calls go behind the supervisor's
# back, so a session never runs them. File contents are out of reach here: a script written
# elsewhere and then run is the supervisor judge's to catch.
KNOWLEDGE_BYPASS_RES = (
    re.compile(r"\bseed_rubric\.py\b"),
    re.compile(r"\b(?:memory_pieces|inbox_entries)\b.*\b(?:insert|update|upsert|delete|rpc)\b", re.I),
    re.compile(r"\b(?:supersede_core_piece|add_core_piece|retire_atom)\b"),
    re.compile(r"/machine/approvals/\d+/answer|/inbox/\d+/answer"),
    # Topics, pieces and shares change only from the app or the MCP tools, never by hand.
    re.compile(
        r"(?=.*-X\s*(?:POST|PATCH|PUT|DELETE)\b).*(?:/subjects/\d+|/pieces/\d+|/workspaces/\d+/subjects)\b"
    ),
)
MAX_EFFECT_COMMAND_CHARS = 400


def _rm_is_destructive(part: str) -> bool:
    if not RM_RECURSIVE_RE.search(part):
        return False
    targets = [token for token in part.split()[1:] if not token.startswith("-")]
    # Build output and scratch dirs are disposable; anything else recursive is not.
    return not targets or not all(RM_SAFE_PATH_RE.search(token) for token in targets)


def command_effects(command: str) -> list[dict]:
    """Per subcommand of a shell line, the strongest effect class it carries."""
    effects: list[dict] = []
    for raw in SUBCOMMAND_SPLIT_RE.split(command or ""):
        part = SUDO_PREFIX_RE.sub("", ENV_PREFIX_RE.sub("", raw.strip()))
        if not part:
            continue
        effect = None
        if any(rule.search(part) for rule in KNOWLEDGE_BYPASS_RES):
            effect = EFFECT_KNOWLEDGE_BYPASS
        elif _rm_is_destructive(part) or any(rule.search(part) for rule in DESTRUCTIVE_RES):
            effect = EFFECT_DESTRUCTIVE
        elif any(rule.search(part) for rule in REMOTE_RES):
            effect = EFFECT_REMOTE
        elif any(rule.search(part) for rule in SHARED_REPO_RES):
            effect = EFFECT_SHARED_REPO
        if effect:
            effects.append({"command": part[:MAX_EFFECT_COMMAND_CHARS], "effect": effect})
    return effects


def _file_text(path: str) -> str:
    try:
        if os.path.getsize(path) > MAX_GUARD_FILE_BYTES:
            return ""
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _new_code(edit: dict) -> str:
    tool, inp = edit["tool"], edit["input"]
    if tool == "Write":
        return inp.get("content") or ""
    if tool == "Edit":
        return inp.get("new_string") or ""
    if tool == "MultiEdit":
        return "\n".join((e or {}).get("new_string") or "" for e in inp.get("edits") or [])
    return ""


def _column_zero_code(edit: dict) -> str:
    """Edit fragments can start mid-line: drop each fragment's first line before
    scanning with column-0 regexes."""
    tool, inp = edit["tool"], edit["input"]
    if tool == "Write":
        return inp.get("content") or ""
    if tool == "Edit":
        return "\n".join((inp.get("new_string") or "").split("\n")[1:])
    if tool == "MultiEdit":
        return "\n".join(
            "\n".join(((e or {}).get("new_string") or "").split("\n")[1:])
            for e in inp.get("edits") or []
        )
    return ""


def _principal_definitions(path: str) -> list[str]:
    """Top-level declarations the file ends up with, in the languages this rubric governs."""
    ext = os.path.splitext(path)[1]
    if ext in (".ts", ".tsx"):
        return TS_EXPORT_DECL_RE.findall(_file_text(path))
    if ext == ".py":
        return PY_TOPLEVEL_CLASS_RE.findall(_file_text(path))
    return []


def principal_definition_guards(paths: list[str]) -> list[dict]:
    """Runs on every file the turn changed, whatever wrote it: an edit tool or a shell
    command. The rule is about the file's final shape, not about how it was edited."""
    findings: list[dict] = []
    for path in sorted(set(paths)):
        if (
            EXEMPT_PATH_RE.search(path)
            or not DECLARATION_DIR_RE.search(path)
            or UTILS_EXEMPT_FILE_RE.search(path)
        ):
            continue
        names = _principal_definitions(path)
        extra = [n for n in names[1:] if not n.endswith(SUPPORTING_TYPE_SUFFIXES)]
        if extra:
            findings.append(
                {
                    "anchor": ANCHOR_ONE_PRINCIPAL,
                    "evidence": (
                        f"{path} declares {len(names)} top-level definitions "
                        f"(`{'`, `'.join(names)}`); `{extra[0]}` is a second principal definition"
                    ),
                    "fix": f"Move `{extra[0]}` to its own file in the same folder.",
                }
            )
    return findings


def code_guards(edits: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for edit in edits:
        path = edit["input"].get("file_path") or ""
        if not path or EXEMPT_PATH_RE.search(path):
            continue
        ext = os.path.splitext(path)[1]
        if ext in RELATIVE_IMPORT_RES:
            for match in RELATIVE_IMPORT_RES[ext].finditer(_new_code(edit)):
                findings.append(
                    {
                        "anchor": ANCHOR_IMPORTS,
                        "evidence": f"relative parent import in {path}: `{match.group(0).strip()}`",
                        "fix": "Use the package/alias form (Dart `package:app/...`, TS `@/...`).",
                    }
                )
        if ext == ".dart":
            for match in DART_ENUM_RE.finditer(_new_code(edit)):
                name = match.group(1)
                if not name.endswith("E"):
                    findings.append(
                        {
                            "anchor": ANCHOR_NAMING,
                            "evidence": f"enum `{name}` in {path} is missing the `E` suffix",
                            "fix": f"Rename to `{name}E` — the suffix applies to every enum.",
                        }
                    )
        if "/utils/" in path and ext in UTILS_FN_RES and not UTILS_EXEMPT_FILE_RE.search(path):
            for match in UTILS_FN_RES[ext].finditer(_column_zero_code(edit)):
                name = match.group(1)
                if name == "main":
                    continue
                findings.append(
                    {
                        "anchor": ANCHOR_UTILS,
                        "evidence": f"top-level function `{name}` in {path}",
                        "fix": "Move it into a `<Domain><Action>Util` class as a static method.",
                    }
                )
    return findings


def _is_finding_title(line: str) -> bool:
    match = BOLD_TITLE_RE.match(line.strip())
    if not match:
        return False
    first_word = re.split(r"[\s:—-]+", match.group(1).strip().lower(), maxsplit=1)[0]
    return first_word not in LABEL_WORDS


def fix_section_check(final_text: str, user_prompt: str) -> list[dict]:
    """Scoped to FORMAL reviews only: verdict-grade markers in the output or an
    explicit review request in the prompt. Progress summaries never match."""
    lines = final_text.split("\n")
    title_idx = [i for i, line in enumerate(lines) if _is_finding_title(line)]
    if len(title_idx) < 2:
        return []
    if not (REVIEW_MARKERS_RE.search(final_text) or REVIEW_REQUEST_RE.search(user_prompt)):
        return []
    findings = []
    for n, start in enumerate(title_idx):
        end = title_idx[n + 1] if n + 1 < len(title_idx) else len(lines)
        block = "\n".join(lines[start + 1 : end])
        if not FIX_LINE_RE.search(block):
            title = lines[start].strip().strip("*")
            findings.append(
                {
                    "anchor": ANCHOR_REVIEW_STRUCTURE,
                    "evidence": f"Finding '{title[:80]}' has no Fix section",
                    "fix": "Add a Fix section with exact changes (files, paths, code shape).",
                }
            )
    return findings


def knowledge_capture_check(user_prompt: str, final_text: str) -> list[dict]:
    prompt = (user_prompt or "").lower()
    if not any(phrase in prompt for phrase in KNOWLEDGE_TRIGGER_PHRASES):
        return []
    if RUBRIC_ADDITION_MARKER in (final_text or "").lower():
        return []
    return [
        {
            "anchor": ANCHOR_KNOWLEDGE_CAPTURE,
            "evidence": (
                "User message contains a correction/durable-preference trigger phrase "
                "but the response has no Rubric addition block"
            ),
            "fix": "End the response with a **Rubric addition** block: target section + exact text.",
        }
    ]


def run(delta: dict, anchors: set[str], changed_paths: list[str] | None = None) -> list[dict]:
    edited = [(e.get("input") or {}).get("file_path") or "" for e in delta.get("edits") or []]
    findings = (
        code_guards(delta.get("edits") or [])
        + principal_definition_guards([p for p in edited if p] + list(changed_paths or []))
        + fix_section_check(delta.get("final_text") or "", delta.get("user_prompt") or "")
        + knowledge_capture_check(delta.get("user_prompt") or "", delta.get("final_text") or "")
    )
    return [finding for finding in findings if finding["anchor"] in anchors]
