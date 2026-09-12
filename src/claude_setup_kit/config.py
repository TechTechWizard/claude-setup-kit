"""Per-repository configuration.

Two files, and the difference between them is the point.

`.claude-setup.toml` is committed. It says which skills are vendored from
elsewhere, which tools wrap an external binary, which paths `~/.claude` links
here. None of it is sensitive; all of it is specific to one repository.

`.claude-setup-private.toml` is never committed and is listed in .gitignore. It
holds the word list for the sanitisation check — client names, colleagues' names,
the home directory of whoever wrote the repository. That list is exactly the kind
of thing the check exists to keep out of a commit, so committing the list itself
would defeat it.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PUBLIC_NAME = ".claude-setup.toml"
PRIVATE_NAME = ".claude-setup-private.toml"


@dataclass
class Config:
    vendored_skills: set[str] = field(default_factory=set)
    doc_only_tools: set[str] = field(default_factory=set)
    linked_paths: tuple[str, ...] = ()
    link_target: str | None = None
    forbidden_words: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    allow_home_paths: bool = False
    skip: set[str] = field(default_factory=set)
    private_found: bool = False

    @classmethod
    def load(cls, root: Path) -> "Config":
        cfg = cls()
        public = _read(root / PUBLIC_NAME)
        cfg.vendored_skills = set(public.get("vendored_skills", []))
        cfg.doc_only_tools = set(public.get("doc_only_tools", []))
        cfg.linked_paths = tuple(public.get("linked_paths", []))
        cfg.link_target = public.get("link_target")
        cfg.allow_home_paths = bool(public.get("allow_home_paths", False))
        cfg.skip = set(public.get("skip", []))

        private = _read(root / PRIVATE_NAME)
        cfg.private_found = bool(private)
        cfg.forbidden_words = list(private.get("forbidden_words", []))
        cfg.forbidden_patterns = list(private.get("forbidden_patterns", []))
        return cfg


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)
