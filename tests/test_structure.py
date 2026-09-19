"""Skills, agents, tools, hooks, settings and the root context."""

from __future__ import annotations

import json

from conftest import find, messages

from claude_setup_kit.structure import (
    check_agents,
    check_hooks_and_settings,
    check_skills,
    check_tools,
)


# --- skills ----------------------------------------------------------------


def test_healthy_skill_passes(skill, repo):
    skill()
    checks = check_skills(repo.root, repo.config())
    assert all(c.passed for c in checks), messages(next(c for c in checks if not c.passed))


def test_no_skills_is_not_applicable(repo):
    checks = check_skills(repo.root, repo.config())
    assert all(not c.applicable for c in checks)
    assert all(c.passed for c in checks), "not applicable must not be reported as failure"


def test_missing_skill_md(repo):
    (repo.root / "skills" / "empty").mkdir(parents=True)
    checks = check_skills(repo.root, repo.config())
    assert not find(checks, "INV-1").passed


def test_frontmatter_must_parse(skill, repo):
    skill(frontmatter="no frontmatter here\n")
    assert not find(check_skills(repo.root, repo.config()), "INV-2").passed


def test_frontmatter_must_be_a_mapping(skill, repo):
    skill(frontmatter="---\n- just\n- a list\n---\n")
    assert not find(check_skills(repo.root, repo.config()), "INV-2").passed


def test_description_may_not_be_empty(skill, repo):
    skill(frontmatter="---\nname: demo\ndescription: \"\"\n---\n")
    assert not find(check_skills(repo.root, repo.config()), "INV-3").passed


def test_name_must_match_directory(skill, repo):
    skill(frontmatter="---\nname: other\ndescription: x\n---\n")
    check = find(check_skills(repo.root, repo.config()), "INV-4")
    assert not check.passed and "other" in messages(check)


def test_unknown_frontmatter_key(skill, repo):
    skill(frontmatter="---\nname: demo\ndescription: x\ninvented: yes\n---\n")
    assert not find(check_skills(repo.root, repo.config()), "INV-5").passed


def test_broken_relative_link(skill, repo):
    skill(body="See [the protocol](protocols/gone.md).\n")
    assert not find(check_skills(repo.root, repo.config()), "INV-6").passed


def test_resolved_relative_link(skill, repo):
    skill(body="See [the protocol](protocols/here.md).\n")
    repo.write("skills/demo/protocols/here.md", "# Here\n")
    assert find(check_skills(repo.root, repo.config()), "INV-6").passed


def test_link_inside_code_is_prose_not_a_reference(skill, repo):
    skill(body="Write it as `[text](missing.md)` in the file.\n")
    assert find(check_skills(repo.root, repo.config()), "INV-6").passed


def test_vendored_skill_is_exempt_from_links(skill, repo):
    skill(name="borrowed", body="[sibling](../gone/SKILL.md)\n")
    cfg = repo.config(vendored_skills={"borrowed"})
    assert find(check_skills(repo.root, cfg), "INV-6").passed


def test_skills_inside_a_plugin_are_found(repo):
    repo.write(
        "plugins/thing/skills/inner/SKILL.md",
        "---\nname: inner\ndescription: x\n---\n",
    )
    checks = check_skills(repo.root, repo.config())
    assert find(checks, "INV-1").applicable
    assert find(checks, "INV-1").examined == 1


# --- agents ----------------------------------------------------------------


def test_healthy_agent_passes(repo):
    repo.write("agents/back.md", "---\nname: back\ndescription: x\ntools: Read, Bash\n---\nbody\n")
    assert all(c.passed for c in check_agents(repo.root, repo.config()))


def test_agent_name_must_match_filename(repo):
    repo.write("agents/back.md", "---\nname: front\ndescription: x\n---\n")
    assert not find(check_agents(repo.root, repo.config()), "INV-9").passed


def test_agent_tools_may_be_absent_but_not_empty(repo):
    repo.write("agents/a.md", "---\nname: a\ndescription: x\n---\n")
    assert find(check_agents(repo.root, repo.config()), "INV-10").passed
    repo.write("agents/b.md", "---\nname: b\ndescription: x\ntools: []\n---\n")
    assert not find(check_agents(repo.root, repo.config()), "INV-10").passed


# --- tools -----------------------------------------------------------------

HELP_SCRIPT = """#!/usr/bin/env python3
import sys
if "--help" in sys.argv:
    print("Demo tool")
    print()
    print("Commands:")
    print("  run    do the thing")
    sys.exit(0)
"""


def test_healthy_tool_passes(repo):
    repo.write("tools/demo/README.md", "# demo\n")
    repo.write("tools/demo/cli.py", HELP_SCRIPT)
    repo.write("CLAUDE.md", "## Tool Index\n\n| Tool | Purpose |\n|---|---|\n| demo | does things |\n")
    checks = check_tools(repo.root, repo.config())
    assert all(c.passed for c in checks), messages(next(c for c in checks if not c.passed))


def test_tool_without_readme(repo):
    repo.write("tools/demo/cli.py", HELP_SCRIPT)
    assert not find(check_tools(repo.root, repo.config()), "INV-11").passed


def test_tool_without_cli_must_be_declared(repo):
    repo.write("tools/wrapper/README.md", "# wrapper\n")
    assert not find(check_tools(repo.root, repo.config()), "INV-12").passed
    cfg = repo.config(doc_only_tools={"wrapper"})
    assert find(check_tools(repo.root, cfg), "INV-12").passed


def test_help_must_list_commands(repo):
    repo.write("tools/demo/README.md", "# demo\n")
    repo.write("tools/demo/cli.py", "#!/usr/bin/env python3\nprint('hello')\n")
    assert not find(check_tools(repo.root, repo.config()), "INV-12").passed


def test_missing_dependency_is_skipped_not_failed(repo):
    repo.write("tools/demo/README.md", "# demo\n")
    repo.write("tools/demo/cli.py", "import nonexistent_package_xyz\n")
    cfg = repo.config(tool_dependencies={"demo": "nonexistent_package_xyz"})
    check = find(check_tools(repo.root, cfg), "INV-12")
    assert check.passed, messages(check)
    assert "skipped" in check.title


def test_syntax_error_in_cli(repo):
    repo.write("tools/demo/README.md", "# demo\n")
    repo.write("tools/demo/cli.py", "def broken(:\n")
    assert not find(check_tools(repo.root, repo.config()), "INV-13").passed


def test_tool_index_both_directions(repo):
    repo.write("tools/demo/README.md", "# demo\n")
    repo.write("tools/demo/cli.py", HELP_SCRIPT)
    repo.write("CLAUDE.md", "## Tool Index\n\n| Tool | Purpose |\n|---|---|\n| gone | removed |\n")
    check = find(check_tools(repo.root, repo.config()), "INV-14")
    assert not check.passed
    assert "demo" in messages(check) and "gone" in messages(check)


# --- hooks, settings, routing ----------------------------------------------


def test_hook_must_be_executable_with_a_shebang(repo):
    repo.write("hooks/ok.sh", "#!/bin/sh\necho ok\n", executable=True)
    assert find(check_hooks_and_settings(repo.root, repo.config()), "INV-15").passed
    repo.write("hooks/bad.sh", "echo no shebang\n")
    assert not find(check_hooks_and_settings(repo.root, repo.config()), "INV-15").passed


def test_settings_must_be_valid_json(repo):
    repo.write("settings.json", "{not json")
    assert not find(check_hooks_and_settings(repo.root, repo.config()), "INV-17").passed


def test_settings_credential(repo):
    repo.write("settings.json", json.dumps({"key": "sk-" + "a" * 30}))
    assert not find(check_hooks_and_settings(repo.root, repo.config()), "INV-18").passed


def test_hook_named_in_settings_must_exist(repo):
    repo.write("settings.json", json.dumps({"hooks": {"S": [{"hooks": [{"command": "bash '/nowhere/hooks/gone.sh'"}]}]}}))
    assert not find(check_hooks_and_settings(repo.root, repo.config()), "INV-16").passed


def test_routing_table_names_a_missing_skill(repo):
    repo.write("skills/here/SKILL.md", "---\nname: here\ndescription: x\n---\n")
    repo.write("CLAUDE.md", "## Skill-first\n\n| Skill | Triggers |\n|---|---|\n| here | a |\n| gone | b |\n")
    check = find(check_hooks_and_settings(repo.root, repo.config()), "INV-19")
    assert not check.passed and "gone" in messages(check)


def test_flat_skill_at_root_is_checked(repo):
    """An Agent Skills repository keeps skills flat at the root, one directory each."""
    repo.write("flat-one/SKILL.md", "---\nname: flat-one\ndescription: A flat skill.\n---\n# Flat\n")
    repo.write("not-a-skill/README.md", "nothing here")
    from claude_setup_kit.structure import skill_dirs
    names = [p.name for p in skill_dirs(repo.root)]
    assert "flat-one" in names
    assert "not-a-skill" not in names
