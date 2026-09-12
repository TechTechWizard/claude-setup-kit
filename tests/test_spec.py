"""The specification and the code must not drift apart."""

from __future__ import annotations

import re
from pathlib import Path

from claude_setup_kit.cli import run
from claude_setup_kit.config import Config

SPEC = Path(__file__).resolve().parents[1] / "SPEC.md"


def implemented():
    return {c.invariant: c.title for c in run(Path("."), Config())}


def documented():
    rows = re.findall(r"^\|\s*`(INV-\d+)`\s*\|\s*(.+?)\s*\|$", SPEC.read_text(), re.MULTILINE)
    return dict(rows)


def test_every_implemented_invariant_is_documented():
    missing = sorted(set(implemented()) - set(documented()), key=lambda s: int(s.split("-")[1]))
    assert not missing, f"implemented but absent from SPEC.md: {missing}"


def test_every_documented_invariant_is_implemented():
    stale = sorted(set(documented()) - set(implemented()), key=lambda s: int(s.split("-")[1]))
    assert not stale, f"documented but not implemented: {stale}"


def test_statements_match_word_for_word():
    impl, doc = implemented(), documented()
    differing = {k: (impl[k], doc[k]) for k in impl if k in doc and impl[k] != doc[k]}
    assert not differing, f"SPEC.md and the code word the same invariant differently: {differing}"
