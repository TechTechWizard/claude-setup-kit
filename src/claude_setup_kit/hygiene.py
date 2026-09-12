"""What must not leave the machine, and what must stay linked to it.

The credential checks are the old ones: a token in a tracked file, a config
directory that got committed. The sanitisation checks are newer and came from a
real leak — task identifiers reached a package that had been reviewed by hand,
and a transcript with local paths reached a commit because an ignore rule was
anchored to the wrong directory. A rule a person has to remember is a rule that
fails on the evening they are tired.
"""

from __future__ import annotations

import re
from pathlib import Path

from .common import Check, Finding, is_text, rel, tracked_files

CREDENTIAL_PATTERNS = [
    ("OpenAI key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("ClickUp token", re.compile(r"pk_[0-9]{5,}_[A-Z0-9]{20,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
]

SESSION_FILE = re.compile(r".*\.(session|session-journal)$")

HOME_PATH = re.compile(r"/(?:Users|home)/[a-z][a-z0-9._-]{1,30}/")

# ClickUp task identifiers. The prefix is stable across a workspace, so this
# catches the shape rather than any particular task.
TASK_ID = re.compile(r"\b86[a-z0-9]{7}\b")

# A placeholder is the point of documentation and must not be mistaken for a leak.
PLACEHOLDER = re.compile(
    r"(your[_-]?token|<[^>]{1,40}>|pk_\.\.\.|sk-\.\.\.|xxx+|example|placeholder)",
    re.IGNORECASE,
)


def check_links(root: Path, cfg) -> list[Check]:
    """INV-20: the paths that ~/.claude links here still link here."""
    check = Check("INV-20", "~/.claude still links into this repository")
    if not cfg.linked_paths:
        check.applicable = False
        return [check]
    base = Path(cfg.link_target).expanduser() if cfg.link_target else Path.home() / ".claude"
    if not base.exists():
        check.applicable = False
        return [check]
    check.examined = len(cfg.linked_paths)
    for name in cfg.linked_paths:
        link = base / name
        target = root / name
        if not link.is_symlink():
            state = "a regular file" if link.exists() else "missing"
            check.findings.append(Finding("INV-20", str(link), f"not a link into this repo — {state}"))
            continue
        if link.resolve() != target.resolve():
            check.findings.append(
                Finding("INV-20", str(link), f"links to {link.resolve()}, expected {target}")
            )
    return [check]


def check_secrets(root: Path, cfg) -> list[Check]:
    files = [p for p in tracked_files(root) if p.is_file()]
    checks = [
        Check("INV-21", "no tracked file matches a credential pattern"),
        Check("INV-22", "nothing under a tool's config/ directory is tracked"),
        Check("INV-23", "no tracked file carries an author's home directory path"),
        Check("INV-24", "no tracked file carries a task identifier"),
        Check("INV-25", "no tracked file carries a name from the private word list"),
    ]
    if not files:
        for check in checks:
            check.applicable = False
        return checks
    for check in checks:
        check.examined = len(files)

    if cfg.allow_home_paths:
        checks[2].applicable = False
    if not cfg.forbidden_words and not cfg.forbidden_patterns:
        checks[4].applicable = False

    words = [
        (word, re.compile(re.escape(word), re.IGNORECASE)) for word in cfg.forbidden_words
    ]
    extra = [(pattern, re.compile(pattern, re.IGNORECASE)) for pattern in cfg.forbidden_patterns]

    for path in files:
        relative = rel(path, root)

        parts = Path(relative).parts
        if ("config" in parts and "tools" in parts) or SESSION_FILE.match(relative):
            checks[1].findings.append(
                Finding("INV-22", relative, "credentials and sessions are never tracked")
            )

        if not is_text(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")

        for label, pattern in CREDENTIAL_PATTERNS:
            for match in pattern.finditer(text):
                if PLACEHOLDER.search(match.group(0)):
                    continue
                checks[0].findings.append(
                    Finding("INV-21", relative, f"{label}: {match.group(0)[:14]}…")
                )

        if checks[2].applicable:
            seen = {m.group(0) for m in HOME_PATH.finditer(text)}
            for found in sorted(seen):
                checks[2].findings.append(
                    Finding("INV-23", relative, f"home directory path: {found}")
                )

        seen_ids = {m.group(0) for m in TASK_ID.finditer(text)}
        for found in sorted(seen_ids):
            checks[3].findings.append(Finding("INV-24", relative, f"task identifier: {found}"))

        if checks[4].applicable:
            for word, pattern in words:
                if pattern.search(text):
                    checks[4].findings.append(Finding("INV-25", relative, f"word: {word}"))
            for source, pattern in extra:
                match = pattern.search(text)
                if match:
                    checks[4].findings.append(
                        Finding("INV-25", relative, f"pattern {source}: {match.group(0)[:30]}")
                    )

    return checks
