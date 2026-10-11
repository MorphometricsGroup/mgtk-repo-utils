# SPDX-License-Identifier: Apache-2.0
import pytest

from mgtk_repo_utils import __version__
from support import PROG, Repo, run_command

TOOLS = ["issues-view", "freeze-lint", "link-check", "resolve", "clone"]


@pytest.mark.parametrize("tool", TOOLS + ["check", "pin"])
def test_every_tool_is_dispatched_and_answers_help(tool):
    result = run_command(tool, "--help")
    assert result.code == 0, result.err
    assert f"usage: {PROG} {tool}" in result.out
    assert "not implemented" not in result.err


def test_unknown_tool_exits_two_with_usage():
    result = run_command("frobnicate")
    assert result.code == 2
    assert "unknown tool" in result.err
    assert "issues-view|freeze-lint|link-check|resolve|clone|check|pin|tools" in result.err


def test_no_arguments_exit_two_with_usage_and_help_exits_zero():
    assert run_command().code == 2
    helped = run_command("--help")
    assert helped.code == 0
    assert "issues-view" in helped.out


def test_version_names_the_one_version_of_the_workspace():
    result = run_command("--version")
    assert result.code == 0
    assert result.out.strip() == f"{PROG} {__version__}"


def test_tools_lists_every_installed_tool_with_its_table_and_distribution():
    result = run_command("tools")
    assert result.code == 0
    rows = [line.split("\t") for line in result.out.splitlines()]
    assert [row[0] for row in rows] == TOOLS + ["check", "pin", "tools"]
    tables = {row[0]: row[1] for row in rows}
    assert tables["issues-view"] == "[issues]"
    assert tables["resolve"] == tables["clone"] == "[clone]"
    assert tables["check"] == "-"
    assert {row[2] for row in rows if row[0] in TOOLS} == {
        "mgtk-repo-utils-issues-view",
        "mgtk-repo-utils-freeze-lint",
        "mgtk-repo-utils-link-check",
        "mgtk-repo-utils-clone",
    }


def test_the_command_runs_from_any_directory_of_the_repository(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", "schema = 1\n[links]\n")
    repo.write("docs/a.md", "ok\n")
    repo.stage()
    result = repo.run("link-check", cwd=repo.root / "docs")
    assert result.code == 0, result.err
    assert "link-check: ok" in result.out
