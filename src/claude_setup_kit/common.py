"""Shared vocabulary for the checks: what a finding is, and how files are read."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Finding:
    """One thing that is wrong, tied to the invariant that says so."""

    invariant: str
    path: str
    message: str


@dataclass
class Check:
    """One invariant and its verdict.

    `applicable` is false when the repository has nothing for this check to look
    at — a marketplace has no `tools/`, a tools repository has no skills. That is
    reported as "not applicable" rather than as a pass, because a check that
    silently passes on an empty directory is how a broken suite goes unnoticed.
    """

    invariant: str
    title: str
    applicable: bool = True
    findings: list[Finding] = field(default_factory=list)
    examined: int = 0

    @property
    def passed(self) -> bool:
        return not self.findings


@dataclass(frozen=True)
class Document:
    """A Markdown file with YAML frontmatter."""

    path: Path
    frontmatter: dict
    body: str


class FrontmatterError(ValueError):
    """The file does not open with a parseable frontmatter block."""


def read_frontmatter(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise FrontmatterError("does not start with a frontmatter block")
    end = text.find("\n---", 3)
    if end == -1:
        raise FrontmatterError("has an unterminated frontmatter block")
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter is not a mapping")
    return Document(path=path, frontmatter=data, body=text[end + 4 :])


_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")


def strip_code(text: str) -> str:
    """Remove fenced and inline code.

    Prose about syntax is not a reference: a path inside backticks is being
    described, not linked, and a checker that cannot tell the difference forces
    authors to stop writing examples.
    """
    return _INLINE.sub("", _FENCE.sub("", text))


def tracked_files(root: Path) -> list[Path]:
    """Files git actually tracks.

    The secrets checks run over this list rather than over the working tree: an
    ignored file is not published, and scanning it produces failures nobody can
    act on.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [root / name for name in out.split("\0") if name]


def is_text(path: Path) -> bool:
    """Whether a file can be read as text at all."""
    try:
        path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    return True


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
