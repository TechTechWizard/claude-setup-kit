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
import subprocess
from fnmatch import fnmatch
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

# ClickUp identifiers. Task ids changed shape once already — nine characters
# opening with 86, then eleven opening with three digits — and a pattern that knew
# only the first shape passed every task id of the second for weeks. So there are
# three nets: both known shapes, any task link whatever the id looks like, and the
# long numeric ids ClickUp gives lists, folders and spaces.
TASK_ID = re.compile(
    r"\b86[a-z0-9]{7}\b"
    r"|\b[0-9]{3}(?=[a-z0-9]*[a-z])[a-z0-9]{8}\b"
    r"|app\.clickup\.com/t/[A-Za-z0-9_-]+"
    r"|\b90[0-9]{7,10}\b"
)

# An address names a person. The only ones allowed are those that name nobody:
# GitHub's noreply form, the co-author line an agent adds, and documentation domains.
# `git@host` is an SSH remote, not a mailbox; a private host in it is the word
# list's business.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ANONYMOUS_EMAIL = re.compile(
    r"(@users\.noreply\.github\.com|^noreply@anthropic\.com|@example\.(com|org|net)|^git@.*)$",
    re.IGNORECASE,
)

# A placeholder is the point of documentation and must not be mistaken for a leak.
PLACEHOLDER = re.compile(
    r"(your[_-]?token|<[^>]{1,40}>|pk_\.\.\.|sk-\.\.\.|xxx+|example|placeholder)",
    re.IGNORECASE,
)

# The escape hatch. A checker that cannot be told "this line is deliberate" forces
# people to either delete a legitimate example or stop reading its output — and the
# second is what actually happens. It has to be on the line itself, so that the
# exemption is visible to whoever reads the line next.
ALLOW = re.compile(r"claude-setup:\s*allow")


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
        Check("INV-28", "no tracked file carries a personal email address"),
    ]
    by_id = {check.invariant: check for check in checks}
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

    words, extra = compile_words(cfg)

    for path in files:
        relative = rel(path, root)
        if any(fnmatch(relative, pattern) for pattern in cfg.exclude_paths):
            continue

        parts = Path(relative).parts
        if ("config" in parts and "tools" in parts) or SESSION_FILE.match(relative):
            checks[1].findings.append(
                Finding("INV-22", relative, "credentials and sessions are never tracked")
            )

        if not is_text(path):
            continue

        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            where = f"{relative}:{number}"
            for invariant, message in scan_line(line, cfg, words, extra):
                target = by_id.get(invariant)
                if target is not None and target.applicable:
                    target.findings.append(Finding(invariant, where, message))

    return checks


def compile_words(cfg):
    words = [
        (word, re.compile(re.escape(word), re.IGNORECASE)) for word in cfg.forbidden_words
    ]
    extra = [(pattern, re.compile(pattern, re.IGNORECASE)) for pattern in cfg.forbidden_patterns]
    return words, extra


def personal_emails(text: str) -> list[str]:
    return [
        m.group(0)
        for m in EMAIL.finditer(text)
        if not ANONYMOUS_EMAIL.search(m.group(0)) and not PLACEHOLDER.search(m.group(0))
    ]


def scan_line(line: str, cfg, words, extra) -> list[tuple[str, str]]:
    """Everything wrong with one line of published text, as (invariant, message)."""
    if ALLOW.search(line):
        return []
    found: list[tuple[str, str]] = []
    for label, pattern in CREDENTIAL_PATTERNS:
        for match in pattern.finditer(line):
            if not PLACEHOLDER.search(match.group(0)):
                found.append(("INV-21", f"{label}: {match.group(0)[:14]}…"))
    if not cfg.allow_home_paths:
        for match in HOME_PATH.finditer(line):
            found.append(("INV-23", f"home directory path: {match.group(0)}"))
    for match in TASK_ID.finditer(line):
        if not PLACEHOLDER.search(match.group(0)):
            found.append(("INV-24", f"task identifier: {match.group(0)}"))
    for word, pattern in words:
        if pattern.search(line):
            found.append(("INV-25", f"word: {word}"))
    for source, pattern in extra:
        match = pattern.search(line)
        if match:
            found.append(("INV-25", f"pattern {source}: {match.group(0)[:30]}"))
    for address in personal_emails(line):
        found.append(("INV-28", f"email address: {address}"))
    return found


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def check_history(root: Path, cfg) -> list[Check]:
    """INV-29 and INV-30: what a public repository publishes is its whole history.

    The file checks above read the last commit, and for months that was taken to
    mean the repository was clean. Anyone who clones it gets every commit, every
    message and every author line, so a value removed from the tree is still
    published until the history is rewritten.
    """
    content = Check("INV-29", "no commit in the history adds a line the file checks would reject")
    meta = Check("INV-30", "no commit message or author line carries personal data")
    log = _git(root, "log", "--all", "--format=%x01%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B")
    if log is None or not log.strip():
        content.applicable = meta.applicable = False
        return [content, meta]
    words, extra = compile_words(cfg)

    commits = [chunk for chunk in log.split("\x01") if chunk.strip()]
    meta.examined = content.examined = len(commits)
    for chunk in commits:
        sha, an, ae, cn, ce, body = (chunk.split("\x00") + [""] * 6)[:6]
        short = sha[:10]
        for role, name, email in (("author", an, ae), ("committer", cn, ce)):
            for address in personal_emails(email):
                meta.findings.append(Finding("INV-30", f"{short} {role}", f"email address: {address}"))
            for word, pattern in words:
                if pattern.search(name):
                    meta.findings.append(Finding("INV-30", f"{short} {role}", f"word: {word}"))
        for number, line in enumerate(body.splitlines(), 1):
            for _, message in scan_line(line, cfg, words, extra):
                meta.findings.append(Finding("INV-30", f"{short} message:{number}", message))

    patch = _git(root, "log", "--all", "-p", "--no-color", "--no-ext-diff", "--format=%x01%H")
    current_sha, current_file = "", ""
    seen: set[tuple[str, str]] = set()
    for line in (patch or "").splitlines():
        if line.startswith("\x01"):
            current_sha = line[1:11]
            continue
        if line.startswith("+++ "):
            current_file = line[6:] if line.startswith("+++ b/") else ""
            continue
        if not line.startswith("+") or not current_file:
            continue
        if any(fnmatch(current_file, pattern) for pattern in cfg.exclude_paths):
            continue
        for _, message in scan_line(line[1:], cfg, words, extra):
            key = (current_file, message)
            if key in seen:
                continue
            seen.add(key)
            content.findings.append(Finding("INV-29", f"{current_sha} {current_file}", message))
    return [content, meta]
