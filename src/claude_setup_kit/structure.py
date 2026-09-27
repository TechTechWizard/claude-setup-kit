"""Structural invariants: skills, agents, tools, hooks, settings, root context.

Every function here returns a Check. A check that finds nothing to look at comes
back not applicable, so that a marketplace repository is not credited with
passing the tool checks it has no tools for.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path

from .common import Check, Finding, FrontmatterError, read_frontmatter, strip_code

# The six fields of the Agent Skills specification — name, description, license,
# compatibility, metadata, allowed-tools — plus the two Claude Code extensions we use.
# `compatibility` was missing until 20.09.2026, so a skill that honestly declared what it
# needs failed the check that exists to catch typos.
KNOWN_SKILL_KEYS = {
    "name",
    "description",
    "allowed-tools",
    "compatibility",
    "disable-model-invocation",
    "license",
    "version",
    "metadata",
}

SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|pk_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{20,})"
)


def skill_dirs(root: Path) -> list[Path]:
    base = root / "skills"
    dirs = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    # A plugin keeps its skills one level deeper, under plugins/<name>/skills/.
    plugins = root / "plugins"
    if plugins.is_dir():
        for plugin in sorted(p for p in plugins.iterdir() if p.is_dir()):
            inner = plugin / "skills"
            if inner.is_dir():
                dirs.extend(sorted(p for p in inner.iterdir() if p.is_dir()))
    # An Agent Skills repository installed with `npx skills` keeps them flat at the
    # root, one directory per skill. Only a directory that already carries a SKILL.md
    # counts here: at the root there is no way to tell an unfinished skill from a
    # directory that was never meant to be one.
    dirs.extend(
        sorted(p for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file() and p not in dirs)
    )
    return dirs


def agent_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for base in (root / "agents", *sorted((root / "plugins").glob("*/agents"))):
        if base.is_dir():
            found.extend(sorted(base.glob("*.md")))
    return found


def tool_dirs(root: Path) -> list[Path]:
    base = root / "tools"
    return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# --- skills ----------------------------------------------------------------


def check_skills(root: Path, cfg) -> list[Check]:
    dirs = skill_dirs(root)
    checks = [
        Check("INV-1", "every skill directory has a readable SKILL.md"),
        Check("INV-2", "every SKILL.md opens with parseable frontmatter"),
        Check("INV-3", "frontmatter carries a non-empty name and description"),
        Check("INV-4", "the name equals the directory name"),
        Check("INV-5", "frontmatter keys come from the known set"),
        Check("INV-6", "relative links inside a skill resolve"),
    ]
    if not dirs:
        for check in checks:
            check.applicable = False
        return checks

    for check in checks:
        check.examined = len(dirs)

    for skill in dirs:
        rel = _rel(skill, root)
        entry = skill / "SKILL.md"
        if not entry.is_file():
            checks[0].findings.append(Finding("INV-1", rel, "no SKILL.md"))
            continue
        try:
            doc = read_frontmatter(entry)
        except FrontmatterError as exc:
            checks[1].findings.append(Finding("INV-2", _rel(entry, root), str(exc)))
            continue

        name = doc.frontmatter.get("name")
        description = doc.frontmatter.get("description")
        if not (isinstance(name, str) and name.strip()):
            checks[2].findings.append(Finding("INV-3", _rel(entry, root), "name is empty or missing"))
        if not (isinstance(description, str) and description.strip()):
            checks[2].findings.append(
                Finding("INV-3", _rel(entry, root), "description is empty or missing")
            )
        if isinstance(name, str) and name != skill.name:
            checks[3].findings.append(
                Finding("INV-4", _rel(entry, root), f"name {name!r} but directory {skill.name!r}")
            )
        unknown = sorted(set(doc.frontmatter) - KNOWN_SKILL_KEYS)
        if unknown:
            checks[4].findings.append(
                Finding("INV-5", _rel(entry, root), f"unknown frontmatter keys: {unknown}")
            )

        if skill.name in cfg.vendored_skills:
            continue
        for md in sorted(skill.rglob("*.md")):
            for target in _relative_links(md.read_text(encoding="utf-8", errors="replace")):
                candidates = [
                    (md.parent / target).resolve(),
                    (root / target.lstrip("/")).resolve(),
                ]
                if not any(c.exists() for c in candidates):
                    checks[5].findings.append(
                        Finding("INV-6", _rel(md, root), f"broken link -> {target}")
                    )
    return checks


def _relative_links(text: str) -> list[str]:
    targets = []
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", strip_code(text)):
        target = match.group(1).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "tel:", "#")):
            continue
        targets.append(target)
    return targets


# --- agents ----------------------------------------------------------------


def check_agents(root: Path, cfg) -> list[Check]:
    files = agent_files(root)
    checks = [
        Check("INV-7", "every agent file opens with parseable frontmatter"),
        Check("INV-8", "frontmatter carries a non-empty name and description"),
        Check("INV-9", "the name equals the filename"),
        Check("INV-10", "tools, when present, is a non-empty string or list"),
    ]
    if not files:
        for check in checks:
            check.applicable = False
        return checks
    for check in checks:
        check.examined = len(files)

    for path in files:
        rel = _rel(path, root)
        try:
            doc = read_frontmatter(path)
        except FrontmatterError as exc:
            checks[0].findings.append(Finding("INV-7", rel, str(exc)))
            continue
        name = doc.frontmatter.get("name")
        description = doc.frontmatter.get("description")
        if not (isinstance(name, str) and name.strip()):
            checks[1].findings.append(Finding("INV-8", rel, "name is empty or missing"))
        if not (isinstance(description, str) and description.strip()):
            checks[1].findings.append(Finding("INV-8", rel, "description is empty or missing"))
        if isinstance(name, str) and name != path.stem:
            checks[2].findings.append(
                Finding("INV-9", rel, f"name {name!r} but file {path.stem!r}")
            )
        if "tools" in doc.frontmatter:
            tools = doc.frontmatter["tools"]
            ok = (isinstance(tools, str) and tools.strip()) or (
                isinstance(tools, list) and tools
            )
            if not ok:
                checks[3].findings.append(Finding("INV-10", rel, "tools is present but empty"))
    return checks


# --- tools -----------------------------------------------------------------


def check_tools(root: Path, cfg) -> list[Check]:
    dirs = tool_dirs(root)
    checks = [
        Check("INV-11", "every tool directory documents itself in README.md"),
        Check("INV-12", "every cli.py answers --help with a command list"),
        Check("INV-13", "every cli.py parses as Python"),
        Check("INV-14", "the CLAUDE.md tool index and tools/ agree in both directions"),
    ]
    if not dirs:
        for check in checks:
            check.applicable = False
        return checks
    for check in checks[:3]:
        check.examined = len(dirs)
    skipped: list[str] = []

    for tool in dirs:
        rel = _rel(tool, root)
        if not (tool / "README.md").is_file():
            checks[0].findings.append(Finding("INV-11", rel, "no README.md"))
        cli = tool / "cli.py"
        if not cli.is_file():
            if tool.name not in cfg.doc_only_tools:
                checks[1].findings.append(
                    Finding(
                        "INV-12",
                        rel,
                        "no cli.py, and the tool is not listed in doc_only_tools",
                    )
                )
            continue
        try:
            ast.parse(cli.read_text(encoding="utf-8"), filename=str(cli))
        except SyntaxError as exc:
            checks[2].findings.append(Finding("INV-13", _rel(cli, root), f"syntax error: {exc}"))
            continue
        result = subprocess.run(
            [cfg.python, str(cli), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONWARNINGS": "ignore"},
        )
        dependency = cfg.tool_dependencies.get(tool.name)
        if result.returncode != 0:
            missing = dependency and f"No module named '{dependency}'" in result.stderr
            if missing:
                # The tool's logic is what the invariant is about, not whether this
                # particular machine has the third-party package installed.
                skipped.append(f"{tool.name} ({dependency} is not installed)")
                continue
            first = (result.stderr.strip().splitlines() or ["(no output)"])[-1]
            checks[1].findings.append(
                Finding("INV-12", _rel(cli, root), f"--help exited {result.returncode}: {first}")
            )
        elif not _lists_commands(result.stdout):
            checks[1].findings.append(
                Finding(
                    "INV-12",
                    _rel(cli, root),
                    "--help printed neither a usage line nor a Commands section",
                )
            )

    if skipped:
        checks[1].title += f" — {len(skipped)} skipped: {', '.join(skipped)}"

    claude_md = root / "CLAUDE.md"
    if not claude_md.is_file():
        checks[3].applicable = False
        return checks
    text = claude_md.read_text(encoding="utf-8")
    section = text.split("## Tool Index", 1)
    if len(section) != 2:
        checks[3].findings.append(Finding("INV-14", "CLAUDE.md", "no '## Tool Index' section"))
        return checks
    listed = _table_keys(section[1].split("\n## ", 1)[0])
    actual = {p.name for p in dirs}
    checks[3].examined = len(actual)
    for missing in sorted(actual - listed):
        checks[3].findings.append(
            Finding("INV-14", "CLAUDE.md", f"tool {missing!r} is absent from the index")
        )
    for stale in sorted(listed - actual):
        checks[3].findings.append(
            Finding("INV-14", "CLAUDE.md", f"index row {stale!r} names no directory under tools/")
        )
    return checks


def _lists_commands(text: str) -> bool:
    """Whether --help actually enumerates commands.

    argparse prints a usage line; a hand-written help prints a Commands section.
    Both are a command list, and demanding one shape would fail tools that read
    perfectly well to a human.
    """
    lowered = text.lower()
    return "usage" in lowered or re.search(r"^\s*commands:", lowered, re.MULTILINE) is not None


def _table_keys(section: str) -> set[str]:
    rows = [line for line in section.splitlines() if line.lstrip().startswith("|")]
    keys = set()
    for row in rows[2:]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if cells and cells[0]:
            keys.add(cells[0])
    return keys


# --- hooks, settings, root context -----------------------------------------


def check_hooks_and_settings(root: Path, cfg) -> list[Check]:
    hooks_dir = root / "hooks"
    settings = root / "settings.json"
    claude_md = root / "CLAUDE.md"
    checks = [
        Check("INV-15", "every hook is executable and starts with a shebang"),
        Check("INV-16", "every hook named in settings.json exists"),
        Check("INV-17", "settings.json is valid JSON"),
        Check("INV-18", "settings.json holds no credential-shaped value"),
        Check("INV-19", "the skill routing table names no skill that is gone"),
    ]

    if hooks_dir.is_dir():
        files = sorted(p for p in hooks_dir.iterdir() if p.is_file())
        checks[0].examined = len(files)
        for path in files:
            rel = _rel(path, root)
            if not os.access(path, os.X_OK):
                checks[0].findings.append(Finding("INV-15", rel, "not executable"))
            head = path.read_bytes()[:2]
            if head != b"#!":
                checks[0].findings.append(Finding("INV-15", rel, "no shebang"))
    else:
        checks[0].applicable = False

    if settings.is_file():
        raw = settings.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            checks[2].findings.append(Finding("INV-17", "settings.json", f"invalid JSON: {exc}"))
            data = None
        checks[2].examined = 1
        if data is not None:
            named = re.findall(r'"command"\s*:\s*"([^"]+)"', raw)
            paths = {
                token
                for command in named
                for token in re.findall(r"[^\s'\"]+/hooks/[^\s'\"]+", command)
            }
            checks[1].examined = len(paths)
            if not paths:
                checks[1].applicable = False
            for candidate in sorted(paths):
                resolved = Path(os.path.expandvars(candidate.replace("~", str(Path.home()))))
                if not resolved.exists():
                    checks[1].findings.append(
                        Finding("INV-16", "settings.json", f"hook path does not exist: {candidate}")
                    )
            found = SECRET_VALUE.findall(raw)
            checks[3].examined = 1
            for value in found:
                checks[3].findings.append(
                    Finding("INV-18", "settings.json", f"credential-shaped value: {value[:12]}…")
                )
    else:
        for index in (1, 2, 3):
            checks[index].applicable = False

    if claude_md.is_file():
        text = claude_md.read_text(encoding="utf-8")
        section = text.split("## Skill-first", 1)
        if len(section) == 2:
            listed = _table_keys(section[1].split("\n## ", 1)[0])
            existing = {p.name for p in skill_dirs(root)}
            checks[4].examined = len(listed)
            for dead in sorted(listed - existing):
                checks[4].findings.append(
                    Finding("INV-19", "CLAUDE.md", f"routing table names a skill that is gone: {dead}")
                )
        else:
            checks[4].applicable = False
    else:
        checks[4].applicable = False

    return checks
