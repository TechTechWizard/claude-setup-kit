"""`claude-setup check` — run every applicable invariant over a repository."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import Check
from .config import Config
from .hygiene import check_links, check_secrets
from .plugins import check_manifests
from .structure import check_agents, check_hooks_and_settings, check_skills, check_tools

CHECKERS = (
    check_skills,
    check_agents,
    check_tools,
    check_hooks_and_settings,
    check_manifests,
    check_links,
    check_secrets,
)

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def run(root: Path, cfg: Config) -> list[Check]:
    checks: list[Check] = []
    for checker in CHECKERS:
        checks.extend(checker(root, cfg))
    for check in checks:
        if check.invariant in cfg.skip:
            check.applicable = False
    return checks


def report(checks: list[Check], root: Path, cfg: Config, colour: bool) -> int:
    def paint(text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if colour else text

    failed = [c for c in checks if c.applicable and not c.passed]
    passed = [c for c in checks if c.applicable and c.passed]
    skipped = [c for c in checks if not c.applicable]

    print(f"claude-setup check {root}\n")
    for check in checks:
        if not check.applicable:
            print(paint(f"  n/a   {check.invariant:<7} {check.title}", DIM))
        elif check.passed:
            count = f" ({check.examined})" if check.examined else ""
            print(paint(f"  ok    {check.invariant:<7} {check.title}{count}", GREEN))
        else:
            print(paint(f"  FAIL  {check.invariant:<7} {check.title}", RED))
            for finding in check.findings[:20]:
                print(f"          {finding.path}: {finding.message}")
            if len(check.findings) > 20:
                print(f"          … and {len(check.findings) - 20} more")

    print()
    if not cfg.private_found:
        print(
            paint(
                "  note  no .claude-setup-private.toml — the word list check has nothing to"
                " check against.",
                DIM,
            )
        )
    summary = f"{len(passed)} passed, {len(failed)} failed, {len(skipped)} not applicable"
    print(paint(summary, RED if failed else GREEN))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-setup",
        description=(
            "Check a Claude Code setup or plugin repository against its contract: "
            "structure, documentation, installation, and nothing leaking that should not."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="run every applicable invariant over a repository")
    check.add_argument(
        "path", nargs="?", default=".", help="repository to check (default: the current directory)"
    )
    check.add_argument("--json", action="store_true", help="machine-readable output")
    check.add_argument("--no-colour", action="store_true", help="plain text, no escape codes")

    sub.add_parser("invariants", help="list the invariants and what each one means")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "invariants":
        cfg = Config()
        for c in run(Path(__file__).resolve().parents[2], cfg):
            print(f"{c.invariant:<7} {c.title}")
        return 0

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"claude-setup: {root} is not a directory", file=sys.stderr)
        return 2
    cfg = Config.load(root)
    checks = run(root, cfg)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "checks": [
                        {
                            "invariant": c.invariant,
                            "title": c.title,
                            "applicable": c.applicable,
                            "passed": c.passed,
                            "examined": c.examined,
                            "findings": [
                                {"path": f.path, "message": f.message} for f in c.findings
                            ],
                        }
                        for c in checks
                    ],
                },
                indent=2,
            )
        )
        return 1 if any(c.applicable and not c.passed for c in checks) else 0

    colour = not args.no_colour and sys.stdout.isatty()
    return report(checks, root, cfg, colour)


if __name__ == "__main__":
    raise SystemExit(main())
