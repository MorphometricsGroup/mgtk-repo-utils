# SPDX-License-Identifier: Apache-2.0
"""pin (design section 10): the hook configuration pins this tool by commit."""

import pytest

from support import COMMIT, CONFIG_FILE, PIN_CONFIG, Repo

OTHER = "89abcdef0123456789abcdef0123456789abcdef"


def repo_with(tmp_path, name: str | None, text: str = PIN_CONFIG, lang: str = "en") -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.write(CONFIG_FILE, f'schema = 1\nlang = "{lang}"\n')
    if name is not None:
        repo.write(name, text)
    return repo


def test_a_frozen_commit_passes(tmp_path):
    result = repo_with(tmp_path, ".pre-commit-config.yaml").run("pin")
    assert (result.code, result.err) == (0, "")
    assert result.out == "pin: ok (1 entry of .pre-commit-config.yaml pin this tool)\n"


@pytest.mark.parametrize("name", [".pre-commit-config.yml", "prek.toml"])
def test_the_other_configuration_files_are_read_too(tmp_path, name):
    text = PIN_CONFIG
    if name.endswith(".toml"):
        text = (
            "[[repos]]\n"
            'repo = "git@example.com:example/mgtk-repo-utils.git"\n'
            f'rev = "{COMMIT}"  # frozen: v0.1.0\n'
            "[[repos.hooks]]\n"
            'id = "mgtk-repo-utils-check"\n'
        )
    result = repo_with(tmp_path, name, text).run("pin")
    assert result.code == 0, result.out
    assert f"of {name} pin" in result.out


def test_prek_toml_wins_over_the_yaml_files(tmp_path):
    repo = repo_with(tmp_path, ".pre-commit-config.yaml")
    repo.write("prek.toml", "repos = []\n")
    result = repo.run("pin")
    assert result.code == 1
    assert "prek.toml: no entry lists a hook of this tool" in result.out


def test_no_configuration_file_is_a_problem(tmp_path):
    result = repo_with(tmp_path, None).run("pin")
    assert result.code == 1
    assert "no hook configuration (prek.toml, .pre-commit-config.yaml, .pre-commit-config.yml)" in result.out


def test_a_configuration_without_this_tool_is_a_problem(tmp_path):
    text = "repos:\n  - repo: local\n    hooks:\n      - id: ruff\n        entry: ruff\n        language: system\n"
    result = repo_with(tmp_path, ".pre-commit-config.yaml", text).run("pin")
    assert result.code == 1
    assert "no entry lists a hook of this tool (an id beginning with `mgtk-repo-utils-`)" in result.out


@pytest.mark.parametrize("rev", ["v0.1.0", "main", COMMIT[:12], COMMIT.upper()])
def test_a_tag_a_branch_a_short_or_an_uppercase_commit_is_a_problem(tmp_path, rev):
    text = PIN_CONFIG.replace(COMMIT, rev)
    result = repo_with(tmp_path, ".pre-commit-config.yaml", text).run("pin")
    assert result.code == 1
    assert f".pre-commit-config.yaml:3: `rev: '{rev}'` is not a full commit" in result.out
    assert "prek update --freeze" in result.out


def test_a_missing_rev_is_a_problem(tmp_path):
    text = PIN_CONFIG.replace(f"    rev: {COMMIT}  # frozen: v0.1.0\n", "")
    result = repo_with(tmp_path, ".pre-commit-config.yaml", text).run("pin")
    assert result.code == 1
    assert "`rev: None` is not a full commit" in result.out


def test_two_entries_pinning_different_commits_are_a_problem(tmp_path):
    text = PIN_CONFIG + PIN_CONFIG.replace(COMMIT, OTHER).replace("repos:\n", "")
    result = repo_with(tmp_path, ".pre-commit-config.yaml", text).run("pin")
    assert result.code == 1
    assert f"pin different commits ({COMMIT[:12]}, {OTHER[:12]})" in result.out


def test_two_entries_pinning_the_same_commit_pass(tmp_path):
    text = PIN_CONFIG + PIN_CONFIG.replace("repos:\n", "")
    result = repo_with(tmp_path, ".pre-commit-config.yaml", text).run("pin")
    assert result.code == 0
    assert "2 entries of" in result.out


def test_a_commit_without_the_frozen_comment_is_a_warning(tmp_path):
    text = PIN_CONFIG.replace("  # frozen: v0.1.0", "")
    result = repo_with(tmp_path, ".pre-commit-config.yaml", text).run("pin")
    assert result.code == 0
    assert "pin: 1 warning(s)" in result.out
    assert ".pre-commit-config.yaml:3: `rev` has no `# frozen: <tag>` comment" in result.out


def test_a_mirror_url_does_not_matter(tmp_path):
    text = PIN_CONFIG.replace("git@example.com:example/mgtk-repo-utils.git", "git@elsewhere.example:m/x.git")
    assert repo_with(tmp_path, ".pre-commit-config.yaml", text).run("pin").code == 0


def test_an_unreadable_configuration_exits_two(tmp_path):
    result = repo_with(tmp_path, ".pre-commit-config.yaml", "repos: [\n").run("pin")
    assert result.code == 2
    assert "mgtk-repo-utils: .pre-commit-config.yaml: cannot read the hook configuration" in result.err


def test_messages_follow_the_configured_language(tmp_path):
    result = repo_with(tmp_path, None, lang="ja").run("pin")
    assert result.code == 1
    assert "hook の設定ファイル" in result.out
