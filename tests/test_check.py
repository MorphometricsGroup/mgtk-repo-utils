# SPDX-License-Identifier: Apache-2.0
from support import BASIC_CONFIG, CONFIG_FILE, README, Repo, add_issue, git, pinned

FREEZE = '[freeze]\npaths = ["frozen"]\nallow = ["frozen/keep.json"]\n'
LINKS = "[links]\n"


def checked(tmp_path, config: str, files: dict[str, str] | None = None) -> Repo:
    repo = pinned(Repo(tmp_path / "repo"))
    repo.write(CONFIG_FILE, config)
    for name, text in (files or {}).items():
        repo.write(name, text)
    repo.stage()
    return repo


def headers(out: str) -> list[str]:
    return [
        line.split(":")[0]
        for line in out.splitlines()
        if line.startswith(("freeze-lint:", "link-check:", "issues-view:", "resolve:", "pin:"))
    ]


def test_every_configured_tool_runs_in_order_then_pin(tmp_path):
    config = BASIC_CONFIG + FREEZE + LINKS
    repo = checked(tmp_path, config, {"frozen/keep.json": "{}", "issues/README.md": README})
    result = repo.run("check")
    assert result.code == 0, result.out
    assert headers(result.out) == ["issues-view", "freeze-lint", "link-check", "pin"]


def test_a_disabled_tool_is_not_run(tmp_path):
    repo = checked(tmp_path, "schema = 1\n" + LINKS, {"README.md": "ok\n"})
    result = repo.run("check")
    assert result.code == 0
    assert headers(result.out) == ["link-check", "pin"]
    assert result.err == ""


def test_with_no_table_only_pin_runs(tmp_path):
    repo = checked(tmp_path, "schema = 1\n")
    result = repo.run("check")
    assert result.code == 0
    assert headers(result.out) == ["pin"]


def test_an_unpinned_repository_fails_check_on_pin_alone(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.write(CONFIG_FILE, "schema = 1\n" + LINKS)
    repo.write("README.md", "ok\n")
    repo.stage()
    result = repo.run("check")
    assert result.code == 1
    assert headers(result.out) == ["link-check", "pin"]
    assert "link-check: ok" in result.out
    assert "pin: 1 problem(s)" in result.out and "no hook configuration" in result.out


def test_the_exit_code_is_the_highest_over_the_tools(tmp_path):
    repo = checked(
        tmp_path, "schema = 1\n" + FREEZE + LINKS, {"frozen/other.json": "{}", "README.md": "ok\n"}
    )
    result = repo.run("check")
    assert result.code == 1
    assert headers(result.out) == ["freeze-lint", "link-check", "pin"]
    assert result.out.splitlines()[0] == "freeze-lint: 1 problem(s)"
    assert "link-check: ok" in result.out


def test_every_tool_failing_still_exits_one_and_prints_every_report(tmp_path):
    repo = checked(
        tmp_path,
        "schema = 1\n" + FREEZE + LINKS,
        {"frozen/other.json": "{}", "README.md": "[a](none.md)\n"},
    )
    result = repo.run("check")
    assert result.code == 1
    assert result.out.count("problem(s)") == 2


def test_issues_view_runs_in_check_mode_and_writes_nothing(tmp_path):
    repo = checked(tmp_path, BASIC_CONFIG, {"issues/README.md": README})
    add_issue(repo, "20260101_a", "open", priority="high")
    git(repo.root, "add", "-f", "issues")
    before = repo.read("issues/README.md")
    result = repo.run("check")
    assert result.code == 1
    assert "issues-view: 1 problem(s)" in result.out
    assert "generated region `issues-active` is out of date" in result.out
    assert repo.read("issues/README.md") == before


def test_a_configuration_error_exits_two_on_standard_error(tmp_path):
    repo = checked(tmp_path, "schema = 1\n[links]\nbogus = 1\n")
    result = repo.run("check")
    assert result.code == 2
    assert "unknown key `links.bogus`" in result.err
    assert result.out == ""


def test_a_missing_configuration_file_exits_two(tmp_path):
    repo = Repo(tmp_path / "repo")
    result = repo.run("check")
    assert result.code == 2
    assert "configuration file not found" in result.err


def test_a_tool_that_exits_two_does_not_stop_the_others_or_pin(tmp_path):
    repo = pinned(Repo(tmp_path / "plain", init=False))
    repo.write(CONFIG_FILE, "schema = 1\n" + FREEZE + LINKS)
    repo.write("README.md", "ok\n")
    result = repo.run("check")
    assert result.code == 2
    assert "not the top level of a git work tree" in result.err
    assert headers(result.out) == ["link-check", "pin"]
