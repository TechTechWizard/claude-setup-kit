"""What must not leave the machine, and what must stay linked to it."""

from __future__ import annotations

from conftest import find, messages

from claude_setup_kit.hygiene import check_links, check_secrets


def test_clean_repository_passes(repo):
    repo.write("README.md", "Nothing to see here.\n")
    repo.commit()
    checks = check_secrets(repo.root, repo.config())
    assert all(c.passed for c in checks), messages(next(c for c in checks if not c.passed))


def test_untracked_files_are_not_scanned(repo):
    repo.write("README.md", "clean\n")
    repo.commit()
    repo.write("secret.txt", "sk-" + "b" * 40)
    check = find(check_secrets(repo.root, repo.config()), "INV-21")
    assert check.passed, "an ignored or untracked file is not published and must not be scanned"


def test_credential_in_a_tracked_file(repo):
    repo.write("notes.md", "token: gh" + "p_" + "c" * 36 + "\n")
    repo.commit()
    assert not find(check_secrets(repo.root, repo.config()), "INV-21").passed


def test_placeholder_is_not_a_credential(repo):
    repo.write("README.md", "echo 'pk_your_personal_token' > ~/.config/clickup/token\n")
    repo.commit()
    assert find(check_secrets(repo.root, repo.config()), "INV-21").passed


def test_private_key_block(repo):
    repo.write("key.pem", "-----BEGIN RSA PRIVATE KEY-----\nabc\n")
    repo.commit()
    assert not find(check_secrets(repo.root, repo.config()), "INV-21").passed


def test_tool_config_directory_must_not_be_tracked(repo):
    repo.write("tools/telegram/config/config.json", "{}\n")
    repo.commit()
    assert not find(check_secrets(repo.root, repo.config()), "INV-22").passed


def test_session_file_must_not_be_tracked(repo):
    repo.write("anywhere/live.session", "x\n")
    repo.commit()
    assert not find(check_secrets(repo.root, repo.config()), "INV-22").passed


def test_home_path_is_caught(repo):
    repo.write("doc.md", "It reads /Users/somebody/Work/thing/file.md at startup.\n")
    repo.commit()
    check = find(check_secrets(repo.root, repo.config()), "INV-23")
    assert not check.passed and "/Users/somebody/" in messages(check)


def test_home_path_may_be_allowed(repo):
    repo.write("doc.md", "/Users/somebody/Work/thing\n")
    repo.commit()
    check = find(check_secrets(repo.root, repo.config(allow_home_paths=True)), "INV-23")
    assert not check.applicable


def test_task_identifier_is_caught(repo):
    repo.write("doc.md", "See https://app.clickup.com/t/86zzz9999 for the details.\n")
    repo.commit()
    check = find(check_secrets(repo.root, repo.config()), "INV-24")
    assert not check.passed and "86zzz9999" in messages(check)


def test_task_placeholder_passes(repo):
    repo.write("doc.md", "See https://app.clickup.com/t/<task-id>.\n")
    repo.commit()
    assert find(check_secrets(repo.root, repo.config()), "INV-24").passed


def test_word_list(repo):
    repo.write("doc.md", "We did this for AcmeCorp last spring.\n")
    repo.commit()
    cfg = repo.config(forbidden_words=["AcmeCorp"])
    check = find(check_secrets(repo.root, cfg), "INV-25")
    assert not check.passed and "AcmeCorp" in messages(check)


def test_word_list_is_case_insensitive(repo):
    repo.write("doc.md", "acmecorp again\n")
    repo.commit()
    assert not find(check_secrets(repo.root, repo.config(forbidden_words=["AcmeCorp"])), "INV-25").passed


def test_word_list_pattern(repo):
    repo.write("doc.md", "list 901504927669 holds the tasks\n")
    repo.commit()
    cfg = repo.config(forbidden_patterns=[r"\b90[0-9]{10}\b"])
    assert not find(check_secrets(repo.root, cfg), "INV-25").passed


def test_word_list_absent_is_not_applicable(repo):
    repo.write("doc.md", "anything\n")
    repo.commit()
    assert not find(check_secrets(repo.root, repo.config()), "INV-25").applicable


def test_binary_files_do_not_break_the_scan(repo):
    (repo.root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")
    repo.write("README.md", "clean\n")
    repo.commit()
    assert all(c.passed for c in check_secrets(repo.root, repo.config()))


def test_links_without_configuration_are_not_applicable(repo):
    assert not check_links(repo.root, repo.config())[0].applicable


def test_link_pointing_elsewhere_is_caught(repo, tmp_path):
    home = tmp_path / "fakehome"
    (home / ".claude").mkdir(parents=True)
    (repo.root / "skills").mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (home / ".claude" / "skills").symlink_to(elsewhere)
    cfg = repo.config(linked_paths=("skills",), link_target=str(home / ".claude"))
    check = check_links(repo.root, cfg)[0]
    assert not check.passed and "elsewhere" in messages(check)


def test_link_that_is_a_regular_file_is_caught(repo, tmp_path):
    home = tmp_path / "fakehome"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("{}")
    repo.write("settings.json", "{}")
    cfg = repo.config(linked_paths=("settings.json",), link_target=str(home / ".claude"))
    check = check_links(repo.root, cfg)[0]
    assert not check.passed and "regular file" in messages(check)


def test_correct_link_passes(repo, tmp_path):
    home = tmp_path / "fakehome"
    (home / ".claude").mkdir(parents=True)
    (repo.root / "skills").mkdir()
    (home / ".claude" / "skills").symlink_to(repo.root / "skills")
    cfg = repo.config(linked_paths=("skills",), link_target=str(home / ".claude"))
    assert check_links(repo.root, cfg)[0].passed


# --- the escape hatches ----------------------------------------------------


def test_excluded_path_is_not_scanned(repo):
    repo.write("tests/fixtures.py", "token = 'gh" + "p_" + "d" * 36 + "'\n")
    repo.commit()
    cfg = repo.config(exclude_paths=["tests/*"])
    assert find(check_secrets(repo.root, cfg), "INV-21").passed


def test_exclusion_is_not_a_blanket(repo):
    repo.write("tests/fixtures.py", "token = 'gh" + "p_" + "e" * 36 + "'\n")
    repo.write("src/leaked.py", "token = 'gh" + "p_" + "f" * 36 + "'\n")
    repo.commit()
    cfg = repo.config(exclude_paths=["tests/*"])
    check = find(check_secrets(repo.root, cfg), "INV-21")
    assert not check.passed
    assert "src/leaked.py" in messages(check) and "tests/" not in messages(check)


def test_allow_marker_exempts_its_own_line(repo):
    repo.write(
        "doc.md",
        "Real: /Users/somebody/Work/x\n"
        "Deliberate: /Users/somebody/Work/y  <!-- claude-setup: allow -->\n",
    )
    repo.commit()
    check = find(check_secrets(repo.root, repo.config()), "INV-23")
    assert not check.passed, "the unmarked line must still be caught"
    assert len(check.findings) == 1, messages(check)
    assert check.findings[0].path.endswith(":1")


def test_findings_name_the_line(repo):
    repo.write("doc.md", "first\nsecond\nhttps://app.clickup.com/t/86zzz9999\n")
    repo.commit()
    check = find(check_secrets(repo.root, repo.config()), "INV-24")
    assert check.findings[0].path.endswith("doc.md:3"), check.findings[0].path
