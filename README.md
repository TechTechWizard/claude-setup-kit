# claude-setup-kit

`claude-setup check` reads a Claude Code repository and tells you what is broken
in it: a skill whose name does not match its directory, a tool missing from the
index, a hook that lost its executable bit, a link into `~/.claude` that quietly
stopped being a link — and a credential, a client name or a task identifier that
is one commit away from leaving your machine.

It works on a personal setup repository, on a plugin marketplace, and on a
repository of command-line tools. Each declares what is particular about it in
`.claude-setup.toml`; the checks that have nothing to look at report themselves as
not applicable rather than passing.

## Install

```sh
uv tool install git+https://github.com/TechTechWizard/claude-setup-kit
claude-setup check .
```

Python 3.11 or newer. The only dependency is PyYAML, for reading frontmatter.

## Use

```sh
claude-setup check                # the current directory
claude-setup check ../marketplace # somewhere else
claude-setup check . --json       # for CI, or for something that reads output
claude-setup invariants           # what it knows how to check
```

It exits 0 when everything applicable passes, 1 when something failed, 2 when the
path is not a directory.

```
claude-setup check ~/Work/claude-pack

  ok    INV-1   every skill directory has a readable SKILL.md (1)
  ok    INV-4   the name equals the directory name (1)
  FAIL  INV-6   relative links inside a skill resolve
          skills/clickup/SKILL.md: broken link -> protocols/gone.md
  n/a   INV-11  every tool directory documents itself in README.md

  12 passed, 1 failed, 14 not applicable
```

## Configuration

`.claude-setup.toml` sits in the repository and is committed:

```toml
vendored_skills = ["skill-creator"]          # copied from elsewhere; exempt from the link check
doc_only_tools  = ["clickup", "gitlab"]      # wrap an external binary, so no cli.py of their own
python          = "/usr/bin/python3"         # the interpreter the tools are written for
linked_paths    = ["skills", "agents"]       # what ~/.claude links here
allow_home_paths = true                      # this repository names its author's directories on purpose
skip = ["INV-25"]                            # an invariant that does not apply here and never will

[tool_dependencies]                          # keep tables last: in TOML every key after a
youtube = "youtube_transcript_api"           # header belongs to that table
```

The word list for the sanitisation check lives apart from all of this, in
`.claude-setup-private.toml` beside the repository or in
`~/.config/claude-setup/private.toml`, and is never committed anywhere:

```toml
forbidden_words = ["AcmeCorp", "A Colleague"]
forbidden_patterns = ["\\b90[0-9]{10}\\b"]
```

An inventory of what must not leak is itself a thing that must not leak, which is
why it is a separate file, why it is in `.gitignore`, and why one copy in your home
directory serves every repository you check.

## What it checks

Twenty-seven invariants, listed with their reasoning in [SPEC.md](SPEC.md). Each
one is proved by a test that breaks a fixture repository on purpose: a check that
has only ever seen healthy input is a function nobody has run.

```sh
uv sync --group dev && uv run pytest
```

## Licence

MIT. See [LICENSE](LICENSE).

## Why it exists

These checks began as a pytest suite inside one person's setup repository, which
meant they could only ever check that repository. Pulling them out made them
useful to anyone with a `~/.claude` worth keeping — and made the three sanitisation
checks possible, which came from two real incidents rather than from imagination.
