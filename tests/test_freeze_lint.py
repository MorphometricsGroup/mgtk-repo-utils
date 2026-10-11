# SPDX-License-Identifier: Apache-2.0
from support import Repo

CONFIG = """\
schema = 1

[freeze]
paths = ["frozen"]
allow = ["frozen/keep.json"]
"""


def frozen_repo(tmp_path, config: str = CONFIG, tracked=("frozen/keep.json",)) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", config)
    for name in tracked:
        repo.write(name, "{}")
    repo.stage()
    return repo


def test_tracked_files_inside_the_allowlist_pass(tmp_path):
    repo = frozen_repo(tmp_path)
    result = repo.run("freeze-lint")
    assert result.code == 0
    assert result.out.strip() == "freeze-lint: ok (1 tracked file(s) under 1 path(s), mode subset)"


def test_subset_fails_on_a_tracked_file_that_is_not_allowed(tmp_path):
    repo = frozen_repo(tmp_path, tracked=("frozen/keep.json", "frozen/sub/other.json"))
    result = repo.run("freeze-lint")
    assert result.code == 1
    assert result.out.splitlines()[0] == "freeze-lint: 1 problem(s)"
    assert result.out.splitlines()[1].startswith(
        "frozen/sub/other.json: tracked under the frozen path `frozen`"
    )
    assert "`git rm --cached`" in result.out


def test_untracked_and_ignored_files_are_never_listed(tmp_path):
    repo = frozen_repo(tmp_path)
    repo.write("frozen/local.json", "{}")
    repo.write(".gitignore", "frozen/ignored.json\n")
    repo.write("frozen/ignored.json", "{}")
    assert repo.run("freeze-lint").code == 0


def test_subset_does_not_fail_on_an_allowed_file_that_is_missing(tmp_path):
    repo = frozen_repo(
        tmp_path,
        tracked=("frozen/readme.txt",),
        config=CONFIG.replace('["frozen/keep.json"]', '["frozen/keep.json", "frozen/readme.txt"]'),
    )
    assert repo.run("freeze-lint").code == 0


def test_exact_also_fails_on_an_allowed_file_that_is_not_tracked(tmp_path):
    config = CONFIG + 'mode = "exact"\n'
    repo = frozen_repo(tmp_path, config, tracked=("frozen/other.json",))
    result = repo.run("freeze-lint")
    assert result.code == 1
    assert result.out.splitlines()[0] == "freeze-lint: 2 problem(s)"
    assert "frozen/keep.json: listed in `allow` but not tracked" in result.out
    assert "frozen/other.json: tracked under the frozen path" in result.out


def test_exact_passes_when_the_tracked_set_equals_the_allowlist(tmp_path):
    repo = frozen_repo(tmp_path, CONFIG + 'mode = "exact"\n')
    assert repo.run("freeze-lint").code == 0


def test_reason_is_appended_to_every_failure_and_not_when_empty(tmp_path):
    config = CONFIG + 'mode = "exact"\nreason = "Equipment lives elsewhere."\n'
    repo = frozen_repo(tmp_path, config, tracked=("frozen/other.json",))
    problems = [
        line for line in repo.run("freeze-lint").out.splitlines() if line.startswith("frozen/")
    ]
    assert len(problems) == 2
    assert all(line.endswith(" Equipment lives elsewhere.") for line in problems)
    plain = frozen_repo(tmp_path / "plain", tracked=("frozen/other.json",))
    assert all(not line.endswith(" ") for line in plain.run("freeze-lint").out.splitlines())


def test_messages_come_from_the_japanese_catalogue(tmp_path):
    repo = frozen_repo(tmp_path, 'lang = "ja"\n' + CONFIG, tracked=("frozen/other.json",))
    result = repo.run("freeze-lint")
    assert result.out.splitlines()[0] == "freeze-lint: 問題 1 件"
    assert "凍結パス `frozen` の下で追跡されている" in result.out


def test_several_paths_and_a_single_file_path(tmp_path):
    config = 'schema = 1\n[freeze]\npaths = ["one", "two/file.txt"]\n'
    repo = frozen_repo(tmp_path, config, tracked=("one/a.txt", "two/file.txt", "two/other.txt"))
    result = repo.run("freeze-lint")
    assert result.code == 1
    assert "one/a.txt: tracked under the frozen path `one`" in result.out
    assert "two/file.txt: tracked under the frozen path `two/file.txt`" in result.out
    assert "two/other.txt" not in result.out


def test_path_names_are_literal_not_globs(tmp_path):
    config = 'schema = 1\n[freeze]\npaths = ["*.txt"]\n'
    repo = frozen_repo(tmp_path, config, tracked=("a.txt",))
    assert repo.run("freeze-lint").code == 0


def test_outside_a_work_tree_exits_two(tmp_path):
    repo = Repo(tmp_path / "plain", init=False)
    repo.write("mgtk-repo-utils.toml", CONFIG)
    result = repo.run("freeze-lint")
    assert result.code == 2
    assert "not the top level of a git work tree" in result.err
    assert result.out == ""


def test_a_root_below_the_top_level_of_a_work_tree_exits_two(tmp_path):
    outer = Repo(tmp_path / "outer")
    inner = outer.root / "inner"
    inner.mkdir()
    (inner / "mgtk-repo-utils.toml").write_text(CONFIG, encoding="utf-8")
    assert outer.run("freeze-lint", "--root", str(inner)).code == 2


def test_missing_paths_is_a_configuration_error(tmp_path):
    repo = frozen_repo(tmp_path, "schema = 1\n[freeze]\nallow = []\n")
    result = repo.run("freeze-lint")
    assert result.code == 2
    assert "`freeze.paths` is required" in result.err


def test_disabled_tool_exits_two(tmp_path):
    repo = frozen_repo(tmp_path, "schema = 1\n")
    result = repo.run("freeze-lint")
    assert result.code == 2
    assert "[freeze] is absent" in result.err
