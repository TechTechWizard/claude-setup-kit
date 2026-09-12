"""Fixtures: a throwaway repository each test can break on purpose.

Every check is verified twice — once on a repository that satisfies it, once on
the same repository with one thing wrong. A check that only ever sees healthy
input is not a check; it is a function nobody has run.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from claude_setup_kit.config import Config


class Repo:
    def __init__(self, root: Path):
        self.root = root

    def write(self, rel: str, text: str, executable: bool = False) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def commit(self) -> None:
        """Track everything. The secrets checks read git, not the working tree."""
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture"], cwd=self.root, check=True, env={**env, "PATH": "/usr/bin:/bin:/usr/local/bin"}
        )

    def config(self, **kwargs) -> Config:
        cfg = Config()
        for key, value in kwargs.items():
            setattr(cfg, key, value)
        return cfg


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


@pytest.fixture
def skill(repo: Repo):
    def make(name: str = "demo", frontmatter: str | None = None, body: str = "# Demo\n") -> Repo:
        front = frontmatter if frontmatter is not None else (
            f"---\nname: {name}\ndescription: A demo skill for the tests.\n---\n"
        )
        repo.write(f"skills/{name}/SKILL.md", front + body)
        return repo

    return make


def find(checks, invariant: str):
    for check in checks:
        if check.invariant == invariant:
            return check
    raise AssertionError(f"no check {invariant} among {[c.invariant for c in checks]}")


def messages(check) -> str:
    return " | ".join(f"{f.path}: {f.message}" for f in check.findings)
