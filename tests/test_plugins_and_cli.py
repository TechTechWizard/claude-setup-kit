"""Plugin manifests, and the command line that ties everything together."""

from __future__ import annotations

import json

from conftest import find, messages

from claude_setup_kit.cli import main, run
from claude_setup_kit.plugins import check_manifests


def marketplace(repo, plugins):
    repo.write(".claude-plugin/marketplace.json", json.dumps({"name": "pack", "plugins": plugins}))


def test_no_manifests_is_not_applicable(repo):
    assert all(not c.applicable for c in check_manifests(repo.root, repo.config()))


def test_healthy_marketplace(repo):
    marketplace(repo, [{"name": "thing", "source": "./plugins/thing"}])
    repo.write("plugins/thing/.claude-plugin/plugin.json", json.dumps({"name": "thing", "description": "x"}))
    assert all(c.passed for c in check_manifests(repo.root, repo.config()))


def test_marketplace_invalid_json(repo):
    repo.write(".claude-plugin/marketplace.json", "{oops")
    assert not find(check_manifests(repo.root, repo.config()), "INV-26").passed


def test_marketplace_entry_points_nowhere(repo):
    marketplace(repo, [{"name": "ghost", "source": "./plugins/ghost"}])
    check = find(check_manifests(repo.root, repo.config()), "INV-26")
    assert not check.passed and "ghost" in messages(check)


def test_marketplace_without_plugins(repo):
    marketplace(repo, [])
    assert not find(check_manifests(repo.root, repo.config()), "INV-26").passed


def test_plugin_manifest_needs_a_description(repo):
    marketplace(repo, [{"name": "thing", "source": "./plugins/thing"}])
    repo.write("plugins/thing/.claude-plugin/plugin.json", json.dumps({"name": "thing"}))
    assert not find(check_manifests(repo.root, repo.config()), "INV-27").passed


def test_plugin_name_must_match_its_directory(repo):
    marketplace(repo, [{"name": "thing", "source": "./plugins/thing"}])
    repo.write("plugins/thing/.claude-plugin/plugin.json", json.dumps({"name": "other", "description": "x"}))
    check = find(check_manifests(repo.root, repo.config()), "INV-27")
    assert not check.passed and "other" in messages(check)


# --- the command line ------------------------------------------------------


def test_every_invariant_has_a_unique_identifier(repo):
    ids = [c.invariant for c in run(repo.root, repo.config())]
    assert len(ids) == len(set(ids)), f"duplicate invariant ids: {ids}"


def test_skip_makes_a_check_not_applicable(repo):
    repo.write("skills/demo/SKILL.md", "---\nname: wrong\ndescription: x\n---\n")
    cfg = repo.config(skip={"INV-4"})
    check = find(run(repo.root, cfg), "INV-4")
    assert not check.applicable


def test_exit_code_is_zero_on_a_clean_repository(repo, capsys):
    repo.write("README.md", "clean\n")
    repo.commit()
    assert main(["check", str(repo.root), "--no-colour"]) == 0
    assert "0 failed" in capsys.readouterr().out


def test_exit_code_is_one_on_a_failure(repo, capsys):
    repo.write("skills/demo/SKILL.md", "---\nname: wrong\ndescription: x\n---\n")
    repo.commit()
    assert main(["check", str(repo.root), "--no-colour"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_missing_directory_exits_two(capsys):
    assert main(["check", "/nowhere/at/all"]) == 2


def test_json_output_is_machine_readable(repo, capsys):
    repo.write("skills/demo/SKILL.md", "---\nname: wrong\ndescription: x\n---\n")
    repo.commit()
    main(["check", str(repo.root), "--json"])
    payload = json.loads(capsys.readouterr().out)
    failed = [c for c in payload["checks"] if c["applicable"] and not c["passed"]]
    assert [c["invariant"] for c in failed] == ["INV-4"]
    assert failed[0]["findings"][0]["path"].endswith("SKILL.md")


def test_no_arguments_prints_help(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()
