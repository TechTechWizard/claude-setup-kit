# What `claude-setup check` enforces

Twenty-seven invariants. Each has an identifier, a one-line statement, and a test
in `tests/` that breaks a fixture repository on purpose to prove the check fires.
An invariant with no test does not belong here.

A check with nothing to look at reports **not applicable** rather than passing. A
marketplace has no `tools/`, a tools repository has no skills, and a suite that
credits them with passing those checks stops meaning anything.

Last reviewed: 2026-09-12.

## Skills

A skill is a directory whose entry point is `SKILL.md`, either under `skills/` or
under `plugins/<name>/skills/`. The description is the whole triggering mechanism
— it is the only part always in context — so it has to say both what the skill
does and the words that summon it.

| Invariant | Statement |
|---|---|
| `INV-1` | every skill directory has a readable SKILL.md |
| `INV-2` | every SKILL.md opens with parseable frontmatter |
| `INV-3` | frontmatter carries a non-empty name and description |
| `INV-4` | the name equals the directory name |
| `INV-5` | frontmatter keys come from the known set |
| `INV-6` | relative links inside a skill resolve |

`INV-4` matters because Claude Code addresses a skill by its directory and reports
it by its frontmatter; a mismatch makes it unaddressable by the name the user sees.
`INV-6` ignores links inside backticks: prose about syntax is an example, not a
reference. Skills listed in `vendored_skills` are exempt from `INV-6` — they were
copied from elsewhere and link to siblings that live where they came from.

## Agents

| Invariant | Statement |
|---|---|
| `INV-7` | every agent file opens with parseable frontmatter |
| `INV-8` | frontmatter carries a non-empty name and description |
| `INV-9` | the name equals the filename |
| `INV-10` | tools, when present, is a non-empty string or list |

`tools` may be absent, and its absence grants every tool — some roles rely on that
deliberately, so the check must not demand the key. What it rejects is a key that
is there and empty, which reads as a restriction and enforces nothing.

## Tools

| Invariant | Statement |
|---|---|
| `INV-11` | every tool directory documents itself in README.md |
| `INV-12` | every cli.py answers --help with a command list |
| `INV-13` | every cli.py parses as Python |
| `INV-14` | the CLAUDE.md tool index and tools/ agree in both directions |

`--help` is how the assistant discovers an interface mid-session, so it has to
answer without touching the network or the user's data. A command list is either
an argparse usage line or a hand-written `Commands:` section; demanding one shape
would fail tools that read perfectly well to a human. A tool whose third-party
dependency is declared in `tool_dependencies` and is not installed is skipped
rather than failed: that is a fact about the machine, not about the tool.

## Hooks, settings, root context

| Invariant | Statement |
|---|---|
| `INV-15` | every hook is executable and starts with a shebang |
| `INV-16` | every hook named in settings.json exists |
| `INV-17` | settings.json is valid JSON |
| `INV-18` | settings.json holds no credential-shaped value |
| `INV-19` | the skill routing table names no skill that is gone |

`INV-19` checks one direction only. The routing table lists the skills whose
triggers are easy to miss, not all of them; a skill absent from it is still found
through its description.

## Installation

| Invariant | Statement |
|---|---|
| `INV-20` | ~/.claude still links into this repository |

Applies only where `linked_paths` is declared and the target directory exists, so
it is silent on CI. It exists for one failure mode: Claude Code rewrites
`settings.json` when a permission is granted or a plugin is toggled, and a rewrite
that renames a temporary file over the target replaces the symbolic link with an
ordinary file. From that moment settings changes stop reaching the repository, and
nothing says so.

## Plugins

| Invariant | Statement |
|---|---|
| `INV-26` | the marketplace manifest parses and lists real plugin directories |
| `INV-27` | every plugin manifest parses and carries name and description |

Claude Code has its own validator and it is the authority. These are the cheap
checks that run everywhere, CI included, where `claude` is not installed.

## What must not leave the machine

| Invariant | Statement |
|---|---|
| `INV-21` | no tracked file matches a credential pattern |
| `INV-22` | nothing under a tool's config/ directory is tracked |
| `INV-23` | no tracked file carries an author's home directory path |
| `INV-24` | no tracked file carries a task identifier |
| `INV-25` | no tracked file carries a name from the private word list |

These run over what git tracks, not over the working tree: an ignored file is not
published, and a finding nobody can act on trains people to ignore the report.

`INV-23` is switched off with `allow_home_paths` in a repository that names its
author's directories on purpose. `INV-24` catches the shape of a ClickUp task id
rather than any particular task. `INV-25` reads the word list from
`.claude-setup-private.toml` beside the repository, or from
`~/.config/claude-setup/private.toml` — and that file is never committed anywhere,
because an inventory of what must not leak is itself a thing that must not leak.

The last three exist because the first two were not enough. Identifiers reached a
package that had been reviewed by hand, and a run's transcripts reached a commit
because an ignore rule was anchored to the wrong directory. A rule a person has to
remember is a rule that fails on the evening they are tired.

## Two ways out

A checker without an escape hatch is a checker people stop reading. There are two,
and both are meant to be visible to whoever reads the code next rather than buried
in a settings file.

`exclude_paths` in `.claude-setup.toml` takes glob patterns and exempts whole
paths from the sanitisation checks. This repository uses it for its own tests: the
tests of a detector must contain the thing it detects, and there is no way around
that.

A `claude-setup: allow` comment anywhere on a line exempts that line, and nothing
else. It is for the documented example that has to look real — a path in a README,
a token shape in a guide.

## Configuration

`.claude-setup.toml`, committed, says what is particular about one repository:
`vendored_skills`, `doc_only_tools`, `tool_dependencies`, `python`,
`linked_paths`, `link_target`, `allow_home_paths`, `exclude_paths`, and `skip`
for an invariant that does not apply here and never will.

`.claude-setup-private.toml`, never committed, carries `forbidden_words` and
`forbidden_patterns`.
