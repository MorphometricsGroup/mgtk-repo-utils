# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from mgtk_repo_utils.files import GitError, is_top_level, list_files, list_untracked, work_tree_top
from support import Repo


def populated(tmp_path) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.write("tracked.md", "t")
    repo.write("dir/also.md", "t")
    repo.stage()
    repo.write("untracked.md", "u")
    repo.write(".gitignore", "ignored.md\n")
    repo.write("ignored.md", "i")
    return repo


def test_tracked_lists_the_index_only(tmp_path):
    repo = populated(tmp_path)
    listing = list_files(repo.root, "tracked")
    assert listing.files == ["dir/also.md", "tracked.md"]
    assert listing.source == "tracked"
    assert listing.missing == []


def test_tracked_lists_a_staged_file_that_is_not_committed(tmp_path):
    repo = populated(tmp_path)
    repo.write("new.md", "n")
    repo.stage("new.md")
    assert "new.md" in list_files(repo.root, "tracked").files


def test_tracked_skips_a_path_deleted_from_the_working_tree_and_reports_it(tmp_path):
    repo = populated(tmp_path)
    (repo.root / "tracked.md").unlink()
    listing = list_files(repo.root, "tracked")
    assert listing.files == ["dir/also.md"]
    assert listing.missing == ["tracked.md"]


def test_worktree_adds_untracked_files_and_honours_ignore_rules(tmp_path):
    repo = populated(tmp_path)
    files = list_files(repo.root, "worktree").files
    assert files == [".gitignore", "dir/also.md", "tracked.md", "untracked.md"]


def test_worktree_drops_files_deleted_from_the_working_tree(tmp_path):
    repo = populated(tmp_path)
    (repo.root / "tracked.md").unlink()
    files = list_files(repo.root, "worktree").files
    assert "tracked.md" not in files
    assert "untracked.md" in files


def test_paths_with_spaces_newlines_and_non_ascii_survive_z_listing(tmp_path):
    repo = Repo(tmp_path / "repo")
    names = ["a b.md", "日本語.md", "line\nbreak.md", 'quo"te.md']
    for name in names:
        repo.write(name)
    repo.stage()
    assert sorted(list_files(repo.root, "tracked").files) == sorted(names)
    assert sorted(list_files(repo.root, "worktree").files) == sorted(names)


def test_untracked_helper_lists_only_untracked_non_ignored_files(tmp_path):
    repo = populated(tmp_path)
    assert list_untracked(repo.root) == [".gitignore", "untracked.md"]


def test_root_that_is_a_work_tree_top_level_is_recognised(tmp_path):
    assert is_top_level(Repo(tmp_path / "repo").root)


def test_plain_directory_uses_the_filesystem_walk_skipping_dot_dirs_and_pycache(tmp_path):
    repo = Repo(tmp_path / "plain", init=False)
    for name in ["a.md", "sub/b.md", ".hidden/c.md", "sub/__pycache__/d.pyc", "sub/.keep"]:
        repo.write(name)
    listing = list_files(repo.root, "tracked")
    assert listing.source == "filesystem"
    assert listing.files == ["a.md", "sub/.keep", "sub/b.md"]


@pytest.mark.parametrize("read", ["tracked", "worktree"])
def test_directory_nested_inside_another_work_tree_uses_the_filesystem_walk(tmp_path, read):
    outer = Repo(tmp_path / "outer")
    outer.write("outside.md")
    outer.stage()
    inner = Repo(outer.root / "inner", init=False)
    inner.write("inside.md")
    assert not is_top_level(inner.root)
    listing = list_files(inner.root, read)
    assert listing.source == "filesystem"
    assert listing.files == ["inside.md"]
    assert list_untracked(inner.root) == []


def test_filesystem_fallback_can_be_refused(tmp_path):
    plain = Repo(tmp_path / "plain", init=False)
    with pytest.raises(GitError, match="work tree"):
        list_files(plain.root, "tracked", fallback=False)


def test_failing_git_command_inside_a_work_tree_is_an_error_not_a_fallback(tmp_path):
    repo = populated(tmp_path)
    (repo.root / ".git" / "index").write_bytes(b"not an index")
    assert os.path.isdir(repo.root / ".git")
    with pytest.raises(GitError):
        list_files(repo.root, "tracked")


def unrunnable_git(tmp_path) -> str:
    """A PATH whose only `git` exists but is not executable."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "git").write_text("#!/bin/sh\nexit 0\n")
    (bindir / "git").chmod(0o644)
    return str(bindir)


def test_a_git_that_cannot_run_is_an_error_not_outside_a_work_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", unrunnable_git(tmp_path))
    with pytest.raises(GitError, match="git cannot be run"):
        work_tree_top(tmp_path)


@pytest.mark.parametrize("tool", ["issues-view", "check"])
def test_every_tool_exits_two_without_a_traceback_when_git_cannot_run(tmp_path, tool):
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", "schema = 1\n[issues]\n")
    result = repo.run(tool, extra_env={"PATH": unrunnable_git(tmp_path)})
    assert result.code == 2
    assert "git cannot be run" in result.err
    assert "Traceback" not in result.err
