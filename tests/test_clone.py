# SPDX-License-Identifier: Apache-2.0
"""clone (design sections 16 and 17): local bare repositories only, no network."""

import ast
import dataclasses
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mgtk_repo_utils.config import load as load_config
from mgtk_repo_utils_clone import clone as clone_module
from mgtk_repo_utils_clone.clone import mask, same_url
from support import PACKAGES, REPO, Repo, git, toml_value

IDENTITY = (
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
    # the developer's global hooks must not run in the fixtures
    "-c",
    "core.hooksPath=/dev/null",
)


def sh(cwd: Path, *args: str) -> str:
    if args[:1] == ("init",):
        args = ("init", "--template=", *args[1:])  # no template hooks either
    return git(cwd, *IDENTITY, *args)


def make_remote(base: Path, name: str) -> Path:
    """A bare repository with one commit on `main`, at `<base>/remotes/<name>.git`."""
    bare = base / "remotes" / f"{name}.git"
    bare.mkdir(parents=True)
    sh(bare, "init", "-q", "--bare", "-b", "main")
    work = base / "scratch" / name
    work.mkdir(parents=True)
    sh(work, "init", "-q", "-b", "main")
    (work / "README").write_text("one\n")
    sh(work, "add", "-A")
    sh(work, "commit", "-q", "-m", "one")
    sh(work, "remote", "add", "origin", str(bare))
    sh(work, "push", "-q", "origin", "main")
    return bare


def push_commit(base: Path, name: str, text: str = "two") -> str:
    """Add a commit to remote `name`, through its scratch clone; returns the new head."""
    work = base / "scratch" / name
    (work / text).write_text(f"{text}\n")
    sh(work, "add", "-A")
    sh(work, "commit", "-q", "-m", text)
    sh(work, "push", "-q", "origin", "main")
    return sh(work, "rev-parse", "HEAD").strip()


def head(path: Path) -> str:
    return sh(path, "rev-parse", "HEAD").strip()


class World:
    """A consumer repository whose registry points at local remotes, and its machine."""

    def __init__(self, base: Path, roots: str = '{ work = "$SRC" }', src: Path | None = None) -> None:
        self.base = base
        self.home = base / "home"
        self.home.mkdir()
        self.src = src or base / "src"
        self.roots = roots
        self.urls = [f"{base}/**"]
        self.repo = Repo(base / "repo")
        self.env: dict[str, str] = {}

    def url(self, name: str) -> str:
        return str(self.base / "remotes" / f"{name}.git")

    def configure(self, *entries: dict, source: dict | None = None) -> None:
        keys = {
            "file": "registry.yaml",
            "entries": "repos[]",
            "root": "work",
            "url": "{url}",
            "id": "name",
            "local": "local",
        } | (source or {})
        self.repo.write(
            "mgtk-repo-utils.toml",
            f'schema = 1\nlang = "en"\n[clone]\nroots = {self.roots}\nurls = {json.dumps(self.urls)}\n'
            "[[clone.sources]]\n" + "".join(f"{k} = {toml_value(v)}\n" for k, v in keys.items()),
        )
        self.repo.write("registry.yaml", json.dumps({"repos": list(entries)}))

    def entry(self, name: str, **extra: str) -> dict:
        return {"name": name, "url": self.url(name)} | extra

    def run(self, *args: str, env: dict[str, str] | None = None):
        base_env = {"HOME": str(self.home), "SRC": str(self.src), "GIT_TERMINAL_PROMPT": "0"}
        return self.repo.run(
            "clone",
            *args,
            extra_env=base_env | self.env | (env or {}),
            drop_env=("XDG_CONFIG_HOME",),  # it would bring back the developer's git configuration
        )


def simple(tmp_path: Path, *names: str, **kwargs) -> World:
    """A world with an existing `$SRC` and a remote and an entry for each name."""
    world = World(tmp_path, **kwargs)
    world.src.mkdir(parents=True, exist_ok=True)
    for name in names:
        make_remote(tmp_path, name)
    world.configure(*(world.entry(name) for name in names))
    return world


def listing(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in path.rglob("*"))


# cloning and updating


def test_a_missing_destination_is_cloned(tmp_path):
    world = simple(tmp_path, "alpha")
    result = world.run("alpha")
    dest = world.src / "alpha"
    assert result.code == 0
    assert result.out == f"clone: ok (cloned alpha to {dest})\n"
    assert "Cloning into" in result.err  # git's own output passes through
    assert (dest / "README").read_text() == "one\n"


def test_a_second_run_reports_present_and_changes_nothing(tmp_path):
    world = simple(tmp_path, "alpha")
    world.run("alpha")
    dest = world.src / "alpha"
    push_commit(tmp_path, "alpha")
    before = (head(dest), listing(dest))
    result = world.run("alpha")
    assert (result.code, result.out) == (0, f"clone: ok (alpha is present at {dest})\n")
    assert (head(dest), listing(dest)) == before
    assert not (dest / ".git" / "FETCH_HEAD").exists()


def test_update_fast_forwards_a_matching_checkout(tmp_path):
    world = simple(tmp_path, "alpha")
    world.run("alpha")
    dest = world.src / "alpha"
    new_head = push_commit(tmp_path, "alpha")
    result = world.run("alpha", "--update")
    assert result.code == 0
    assert result.out.endswith(f"clone: ok (updated alpha at {dest})\n")
    assert "Fast-forward" in result.out  # git's own output passes through
    assert head(dest) == new_head


def test_update_on_a_diverged_checkout_exits_one_and_keeps_head(tmp_path):
    world = simple(tmp_path, "alpha")
    world.run("alpha")
    dest = world.src / "alpha"
    sh(dest, "commit", "-q", "--allow-empty", "-m", "local")
    local = head(dest)
    push_commit(tmp_path, "alpha")
    result = world.run("alpha", "--update")
    assert result.code == 1
    assert "clone: 1 problem(s)" in result.out and "exited with 128" in result.out
    assert head(dest) == local


def test_update_never_fetches_from_the_remote_the_branch_tracks_instead_of_origin(tmp_path):
    world = simple(tmp_path, "alpha")
    other = make_remote(tmp_path, "other")
    world.run("alpha")
    dest = world.src / "alpha"
    push_commit(tmp_path, "other")
    sh(dest, "remote", "add", "other", str(other))
    sh(dest, "config", "branch.main.remote", "other")
    sh(dest, "config", "branch.main.merge", "refs/heads/main")
    before = head(dest)
    push_commit(tmp_path, "alpha")
    result = world.run("alpha", "--update")
    assert result.code == 1
    assert head(dest) == before
    refs = sh(dest, "for-each-ref", "refs/remotes/other")
    assert refs == ""


def test_a_failed_clone_exits_one_whatever_git_returned(tmp_path):
    world = simple(tmp_path)
    world.configure(world.entry("ghost"))  # no such remote
    result = world.run("ghost")
    assert result.code == 1
    assert "`git clone` exited with" in result.out
    assert not (world.src / "ghost").exists()


# origin


def checkout(tmp_path: Path, name: str = "alpha") -> tuple[World, Path]:
    world = simple(tmp_path, name)
    assert world.run(name).code == 0
    return world, world.src / name


def test_a_different_origin_is_reported_with_both_urls_and_the_remedy(tmp_path):
    world, dest = checkout(tmp_path)
    elsewhere = make_remote(tmp_path, "elsewhere")
    sh(dest, "remote", "set-url", "origin", str(elsewhere))
    result = world.run("alpha")
    assert result.code == 1
    assert str(elsewhere) in result.out and world.url("alpha") in result.out
    remedy = f"git -C {shlex.quote(str(dest))} remote set-url origin {shlex.quote(world.url('alpha'))}"
    assert remedy in result.out


def test_a_different_origin_is_never_pulled_with_update(tmp_path):
    world, dest = checkout(tmp_path)
    sh(dest, "remote", "set-url", "origin", str(make_remote(tmp_path, "elsewhere")))
    before = head(dest)
    push_commit(tmp_path, "elsewhere")
    result = world.run("alpha", "--update")
    assert result.code == 1
    assert head(dest) == before
    assert not (dest / ".git" / "FETCH_HEAD").exists()
    assert sh(dest, "config", "remote.origin.url").strip() == str(tmp_path / "remotes" / "elsewhere.git")


def test_a_checkout_without_origin_is_reported_with_the_remote_add_remedy(tmp_path):
    world, dest = checkout(tmp_path)
    sh(dest, "remote", "remove", "origin")
    result = world.run("alpha", "--update")
    assert result.code == 1
    assert f"git -C {shlex.quote(str(dest))} remote add origin {shlex.quote(world.url('alpha'))}" in result.out
    assert sh(dest, "remote") == ""


def test_several_origin_urls_are_reported_and_not_pulled(tmp_path):
    world, dest = checkout(tmp_path)
    sh(dest, "config", "--add", "remote.origin.url", "/srv/example/other.git")
    result = world.run("alpha", "--update")
    assert result.code == 1
    assert "several `origin` URLs" in result.out and "/srv/example/other.git" in result.out
    assert not (dest / ".git" / "FETCH_HEAD").exists()


def test_user_configuration_that_rewrites_urls_does_not_cause_a_mismatch(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    make_remote(tmp_path, "alpha")
    world.urls.append("ex:*")
    (world.home / ".gitconfig").write_text(
        f'[url "{tmp_path}/remotes/"]\n\tinsteadOf = ex:\n'
    )
    world.configure({"name": "alpha", "url": "ex:alpha.git"})
    first = world.run("alpha")
    dest = world.src / "alpha"
    assert first.code == 0, first.out + first.err
    assert sh(dest, "config", "remote.origin.url").strip() == "ex:alpha.git"
    second = world.run("alpha")
    assert (second.code, second.out) == (0, f"clone: ok (alpha is present at {dest})\n")


@pytest.mark.parametrize(
    "first, second",
    [
        ("git@example.com:o/r.git", "ssh://git@example.com/o/r"),
        ("git@example.com:o/r.git", "ssh://example.com:22/o/r.git/"),
        ("git@example.com:o/r.git", "https://example.com/o/r"),
        ("https://Example.com:443/o/r.git", "git@example.com:o/r"),
        ("https://user:secret@example.com/o/r", "https://example.com/o/r"),
        ("git@EXAMPLE.com:o/r", "git@example.com:o/r"),
        ("ssh://h:2222/o/r", "ssh://other@h:2222/o/r/"),
        ("git@h:x", "ssh://git@h/x"),
        ("git@h:x", "ssh://h/x"),
        ("h:x", "alice@h:x"),
        ("alice@h:x", "https://h/x"),
        ("alice@h:x", "alice@h:x.git"),
        ("git@h:/o/r", "git@h:o/r"),
        ("/srv/x/", "/srv/x"),
        ("http://h/o/r", "http://h/o/r/"),
    ],
)
def test_spellings_of_one_repository_compare_equal(first, second):
    assert same_url(first, second) and same_url(second, first)


@pytest.mark.parametrize(
    "first, second",
    [
        ("ssh://h:2222/o/r", "git@h:o/r"),
        ("https://h:8443/o/r", "https://h/o/r"),
        ("https://h:22/o/r", "ssh://h/o/r"),
        ("ssh://h:443/o/r", "https://h/o/r"),
        ("git@h:O/r", "git@h:o/r"),
        ("git@h:o/r", "git@h2:o/r"),
        ("git@h:o/r.git", "git@h:o/r.git.git"),
        ("file:///srv/x", "/srv/x"),
        ("/srv/x", "/srv/y"),
        ("/srv/x//", "/srv/x"),
        ("http://h/o/r", "https://h/o/r"),
        ("ssh://h/o/r?a=1", "ssh://h/o/r"),
        ("alice@h:repo.git", "bob@h:repo.git"),
        ("ssh://alice@h/x", "bob@h:x"),
        ("ssh://alice@h/x", "ssh://bob@h/x"),
    ],
)
def test_different_repositories_compare_unequal(first, second):
    assert not same_url(first, second)


@pytest.mark.parametrize(
    "url, masked",
    [
        ("https://token@example.com/o/r", "https://***@example.com/o/r"),
        ("https://user:secret@example.com:8443/o/r", "https://user:***@example.com:8443/o/r"),
        ("ssh://user:secret@example.com/o/r", "ssh://user:***@example.com/o/r"),
        ("ssh://git@example.com/o/r", "ssh://git@example.com/o/r"),
        ("git+ssh://git@example.com/o/r", "git+ssh://git@example.com/o/r"),
        ("ssh+git://git@example.com/o/r", "ssh+git://git@example.com/o/r"),
        ("SSH://git@example.com/o/r", "SSH://git@example.com/o/r"),
        ("http://TOKEN@example.com/o/r", "http://***@example.com/o/r"),
        ("ftp://TOKEN@example.com/o/r", "ftp://***@example.com/o/r"),
        ("git://TOKEN@example.com/o/r", "git://***@example.com/o/r"),
        ("http://user:secret@example.com/o/r", "http://user:***@example.com/o/r"),
        ("git@example.com:o/r", "git@example.com:o/r"),
        ("https://example.com/o/r", "https://example.com/o/r"),
        ("/srv/x", "/srv/x"),
    ],
)
def test_a_credential_in_the_user_part_is_masked(url, masked):
    assert mask(url) == masked


def test_a_token_in_an_origin_url_is_masked_in_the_mismatch_report(tmp_path):
    world, dest = checkout(tmp_path)
    sh(dest, "remote", "set-url", "origin", "https://ghp_SECRET@example.com/o/r.git")
    result = world.run("alpha", "--update")
    assert result.code == 1
    assert "ghp_SECRET" not in result.out + result.err
    assert "https://***@example.com/o/r.git" in result.out


# containment


def test_a_missing_root_exits_two_with_the_mkdir_remedy_and_creates_nothing(tmp_path):
    world = World(tmp_path)
    make_remote(tmp_path, "alpha")
    world.configure(world.entry("alpha"))
    result = world.run("alpha")
    assert result.code == 2
    assert f"mkdir -p {world.src}" in result.err
    assert not world.src.exists()


def test_a_deviation_in_a_missing_root_blames_the_root_not_the_declaration(tmp_path):
    world = World(tmp_path)
    make_remote(tmp_path, "alpha")
    world.configure(world.entry("alpha", local="$SRC/deep/alpha"))
    result = world.run("alpha")
    assert result.code == 2
    assert "root `work` is not an existing directory" in result.err
    assert f"mkdir -p {world.src}" in result.err
    assert not world.src.exists()


def test_a_deviations_missing_parent_exits_two_with_the_mkdir_remedy(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    make_remote(tmp_path, "alpha")
    world.configure(world.entry("alpha", local="$SRC/deep/alpha"))
    result = world.run("alpha")
    assert result.code == 2
    assert "parent of the declared destination" in result.err
    assert f"mkdir -p {world.src / 'deep'}" in result.err
    assert listing(world.src) == []


def test_a_destination_under_a_symlink_that_escapes_the_root_is_refused(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (world.src / "link").symlink_to(outside)
    make_remote(tmp_path, "alpha")
    world.configure(world.entry("alpha", local="$SRC/link/alpha"))
    result = world.run("alpha")
    assert result.code == 1
    assert "not strictly inside root `work`" in result.out
    assert listing(outside) == []


def test_a_dangling_symlink_destination_pointing_outside_the_root_is_refused(tmp_path):
    world = simple(tmp_path, "alpha")
    (world.src / "alpha").symlink_to(tmp_path / "nowhere")
    result = world.run("alpha")
    assert result.code == 1
    assert "not strictly inside root `work`" in result.out
    assert not (tmp_path / "nowhere").exists()


def test_a_root_that_is_a_symlink_to_another_directory_works(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    world = simple(tmp_path, "alpha", src=link)
    assert world.run("alpha").code == 0
    assert (real / "alpha" / "README").exists()
    again = world.run("alpha")
    assert (again.code, again.out) == (0, f"clone: ok (alpha is present at {link / 'alpha'})\n")


def two_roots(tmp_path: Path, other: str) -> World:
    world = World(tmp_path, roots='{ work = "$SRC", ops = "$OPS" }')
    world.src.mkdir()
    make_remote(tmp_path, "x")
    world.env["OPS"] = other
    world.configure(world.entry("x"))
    return world


def test_a_destination_equal_to_another_root_on_this_machine_is_refused(tmp_path):
    world = two_roots(tmp_path, str(tmp_path / "src" / "x"))
    result = world.run("x")
    assert result.code == 1
    assert "equals or contains root `ops`" in result.out
    assert listing(world.src) == []


def test_a_destination_containing_another_root_on_this_machine_is_refused(tmp_path):
    world = two_roots(tmp_path, str(tmp_path / "src" / "x" / "y"))
    result = world.run("x")
    assert result.code == 1
    assert "equals or contains root `ops`" in result.out
    assert listing(world.src) == []


def test_another_root_is_compared_without_regard_to_case_or_normalisation(tmp_path):
    # where the filesystem ignores case, `realpath` keeps the spelling it was given
    world = two_roots(tmp_path, str(tmp_path / "src" / "X"))
    result = world.run("x")
    assert result.code == 1
    assert "equals or contains root `ops`" in result.out
    assert listing(world.src) == []


def test_a_root_whose_variable_is_unset_is_skipped_by_containment(tmp_path):
    world = World(tmp_path, roots='{ work = "$SRC", ops = "$OPS" }')
    world.src.mkdir()
    make_remote(tmp_path, "x")
    world.configure(world.entry("x"))
    assert world.run("x").code == 0


# existing destinations


def add_worktree(tmp_path: Path, world: World, name: str = "alpha") -> Path:
    """A linked worktree at the destination, whose repository lies outside the root."""
    main = tmp_path / "outside" / name
    sh(tmp_path, "clone", "-q", world.url(name), str(main))
    sh(main, "worktree", "add", "-q", "-b", "linked", str(world.src / name))
    return main


@pytest.mark.parametrize("args", [(), ("--update",)])
def test_a_linked_worktree_whose_repository_is_outside_the_root_is_refused(tmp_path, args):
    world = simple(tmp_path, "alpha")
    main = add_worktree(tmp_path, world)
    push_commit(tmp_path, "alpha")
    result = world.run("alpha", *args)
    assert result.code == 1
    assert "keeps its repository data outside root `work`" in result.out
    assert str(main / ".git") in result.out
    assert list(tmp_path.rglob("FETCH_HEAD")) == []


def test_a_symlink_to_an_outside_checkout_of_the_same_repository_is_not_updated(tmp_path):
    world = simple(tmp_path, "alpha")
    outside = tmp_path / "outside" / "alpha"
    sh(tmp_path, "clone", "-q", world.url("alpha"), str(outside))
    (world.src / "alpha").symlink_to(outside)
    push_commit(tmp_path, "alpha")
    before = head(outside)
    result = world.run("alpha", "--update")
    assert result.code == 1
    assert "not strictly inside root `work`" in result.out
    assert head(outside) == before
    assert list(tmp_path.rglob("FETCH_HEAD")) == []


def test_a_file_at_the_destination_is_refused_and_left_alone(tmp_path):
    world = simple(tmp_path, "alpha")
    (world.src / "alpha").write_text("mine\n")
    result = world.run("alpha", "--update")
    assert result.code == 1 and "is a file" in result.out
    assert (world.src / "alpha").read_text() == "mine\n"


def test_an_empty_directory_is_reported_with_the_rmdir_remedy_and_kept(tmp_path):
    world = simple(tmp_path, "alpha")
    (world.src / "alpha").mkdir()
    result = world.run("alpha")
    assert result.code == 1
    assert f"rmdir {shlex.quote(str(world.src / 'alpha'))}" in result.out
    assert (world.src / "alpha").is_dir() and listing(world.src / "alpha") == []


def test_a_dangling_symlink_inside_the_root_is_refused_and_kept(tmp_path):
    world = simple(tmp_path, "alpha")
    link = world.src / "alpha"
    link.symlink_to(world.src / "missing")
    result = world.run("alpha")
    assert result.code == 1 and "dangling symlink" in result.out
    assert link.is_symlink() and os.readlink(link) == str(world.src / "missing")
    assert not (world.src / "missing").exists()


def test_a_bare_repository_at_the_destination_is_refused_and_left_alone(tmp_path):
    world = simple(tmp_path, "alpha")
    dest = world.src / "alpha"
    dest.mkdir()
    sh(dest, "init", "-q", "--bare")
    before = listing(dest)
    result = world.run("alpha", "--update")
    assert result.code == 1 and "bare repository" in result.out
    assert listing(dest) == before


def test_a_plain_directory_inside_an_enclosing_work_tree_is_not_a_checkout(tmp_path):
    enclosing = tmp_path / "enclosing"
    enclosing.mkdir()
    sh(enclosing, "init", "-q", "-b", "main")
    world = simple(tmp_path, "alpha", src=enclosing / "src")
    (world.src / "alpha").mkdir()
    (world.src / "alpha" / "note").write_text("mine\n")
    result = world.run("alpha", "--update")
    assert result.code == 1 and "inside another work tree" in result.out
    assert listing(world.src / "alpha") == ["note"]
    assert sh(enclosing, "remote") == ""


def test_a_directory_that_is_not_a_checkout_is_refused_and_left_alone(tmp_path):
    world = simple(tmp_path, "alpha")
    (world.src / "alpha").mkdir()
    (world.src / "alpha" / "note").write_text("mine\n")
    result = world.run("alpha")
    assert result.code == 1 and "is not the top of a checkout" in result.out
    assert listing(world.src / "alpha") == ["note"]


# URLs


def wrapped_git(base: Path) -> tuple[dict[str, str], Path]:
    """A `git` first on PATH that logs argv and environment of each call, then runs the real one."""
    real = shutil.which("git")
    assert real
    log = base / "git.log"
    bindir = base / "bin"
    bindir.mkdir()
    script = bindir / "git"
    script.write_text(
        "#!/bin/sh\n"
        "{ echo CALL; for a in \"$@\"; do printf 'ARG %s\\n' \"$a\"; done; echo ENV; env; echo END; }"
        f" >> {shlex.quote(str(log))}\n"
        f"exec {shlex.quote(real)} \"$@\"\n"
    )
    script.chmod(0o755)
    return {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}, log


def recorded(log: Path) -> list[tuple[list[str], dict[str, str]]]:
    calls: list[tuple[list[str], dict[str, str]]] = []
    if not log.exists():
        return calls
    argv: list[str] = []
    env: dict[str, str] = {}
    section = ""
    for line in log.read_text().splitlines():
        if line == "CALL":
            argv, env, section = [], {}, "arg"
        elif line == "ENV":
            section = "env"
        elif line == "END":
            calls.append((argv, env))
            section = ""
        elif section == "arg" and line.startswith("ARG "):
            argv.append(line[4:])
        elif section == "env" and "=" in line:
            key, _, value = line.partition("=")
            env[key] = value
    return calls


def destination_calls(log: Path, dest: Path) -> list[tuple[list[str], dict[str, str]]]:
    return [
        (argv, env)
        for argv, env in recorded(log)
        if argv[:1] == ["clone"] or argv[:2] == ["-C", str(dest)]
    ]


def test_a_url_beginning_with_a_dash_reaches_git_only_as_an_argument_after_the_separator(
    tmp_path, monkeypatch
):
    # No `urls` pattern may begin with `-` (design section 13), so no configuration can
    # deliver such a URL; `--` is the second guard, so the entry is forged in-process.
    world = simple(tmp_path, "alpha")
    real_load = clone_module.registry.load

    def forged_load(config, tool):
        resolution = real_load(config, tool)
        entry = dataclasses.replace(resolution.find("alpha"), url="--template=example:alpha")
        return dataclasses.replace(resolution, _by_name={"alpha": entry})

    calls: list[list[str]] = []

    def fake_run(argv, env, *, capture):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 128, b"", b"")

    monkeypatch.setattr(clone_module.registry, "load", forged_load)
    monkeypatch.setattr(clone_module, "_run", fake_run)
    monkeypatch.setattr(clone_module, "_dropped_names", lambda: frozenset({"GIT_DIR"}))
    monkeypatch.setenv("SRC", str(world.src))
    config = load_config(world.repo.root / "mgtk-repo-utils.toml", world.repo.root)
    _, code = clone_module.run(config, "alpha", False)
    assert code == 1
    assert ["git", "clone", "--", "--template=example:alpha", str(world.src / "alpha")] in calls
    assert not (world.src / "alpha").exists()


def test_a_url_outside_urls_never_reaches_git(tmp_path):
    world = simple(tmp_path, "alpha")
    world.configure({"name": "alpha", "url": "/srv/example/alpha.git"})
    env, log = wrapped_git(tmp_path)
    result = world.run("alpha", env=env)
    assert result.code == 1
    assert "matches no pattern of `clone.urls`" in result.out
    assert not any(argv[:1] == ["clone"] for argv, _ in recorded(log))
    assert listing(world.src) == []


def test_shell_metacharacters_in_a_destination_are_quoted_in_the_printed_remedy(tmp_path):
    name = "a;b$HOME'c"
    world = simple(tmp_path, name)
    (world.src / name).mkdir()
    result = world.run(name)
    assert result.code == 1
    assert f"rmdir {shlex.quote(str(world.src / name))}" in result.out


def test_shell_metacharacters_in_a_url_are_quoted_in_the_printed_remedy(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    url = f"{tmp_path}/remotes/a;$(x)'b.git"
    world.configure({"name": "alpha", "url": url})
    dest = world.src / "alpha"
    dest.mkdir()
    sh(dest, "init", "-q", "-b", "main")
    sh(dest, "remote", "add", "origin", "/srv/example/other.git")
    result = world.run("alpha")
    assert result.code == 1
    assert f"remote set-url origin {shlex.quote(url)}" in result.out


# environment


def test_git_calls_on_a_destination_drop_the_locating_variables_and_keep_the_others(tmp_path):
    world = simple(tmp_path, "alpha")
    consumer = world.repo.root
    config_before = (consumer / ".git" / "config").read_text()
    wrapper, log = wrapped_git(tmp_path)
    env = wrapper | {
        "GIT_DIR": str(consumer / ".git"),
        "GIT_WORK_TREE": str(consumer),
        "GIT_INDEX_FILE": str(consumer / ".git" / "index"),
        "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
        "GIT_CONFIG_PARAMETERS": "'core.abbrev'='9'",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.abbrev",
        "GIT_CONFIG_VALUE_0": "9",
        "GIT_TERMINAL_PROMPT": "0",
        "KIT_TEST_CUSTOM": "kept",
    }
    dest = world.src / "alpha"
    assert world.run("alpha", env=env).code == 0
    push_commit(tmp_path, "alpha")
    assert world.run("alpha", "--update", env=env).code == 0
    calls = destination_calls(log, dest)
    verbs = [argv[2] if argv[0] == "-C" else argv[0] for argv, _ in calls]
    assert verbs == ["clone", "rev-parse", "rev-parse", "config", "pull"]
    for _, seen in calls:
        assert not {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} & set(seen)
        assert seen["GIT_SSH_COMMAND"] == "ssh -o BatchMode=yes"
        assert seen["GIT_CONFIG_PARAMETERS"] == "'core.abbrev'='9'"
        assert (seen["GIT_CONFIG_COUNT"], seen["GIT_CONFIG_KEY_0"]) == ("1", "core.abbrev")
        assert seen["KIT_TEST_CUSTOM"] == "kept" and seen["HOME"] == str(world.home)
    assert (dest / "README").exists() and (dest / "two").exists()
    assert (consumer / ".git" / "config").read_text() == config_before
    assert not (consumer / ".git" / "FETCH_HEAD").exists()
    assert git(consumer, "remote") == ""


def test_the_list_of_variables_to_drop_is_asked_of_git_without_any_git_variable(tmp_path):
    world = simple(tmp_path, "alpha")
    wrapper, log = wrapped_git(tmp_path)
    env = wrapper | {"GIT_DIR": "/nonexistent/bogus", "GIT_WORK_TREE": "/nonexistent/bogus"}
    assert world.run("alpha", env=env).code == 0
    asked = [seen for argv, seen in recorded(log) if argv == ["rev-parse", "--local-env-vars"]]
    assert len(asked) == 1
    assert not [name for name in asked[0] if name.startswith("GIT_")]


def test_a_git_that_cannot_be_executed_exits_two_naming_the_error(tmp_path):
    world = simple(tmp_path, "alpha")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "git").write_text("#!/bin/sh\n")
    (bindir / "git").chmod(0o644)
    # `--root` keeps the root lookup (files.work_tree_top, which also runs git) out of the way
    result = world.run("alpha", "--root", str(world.repo.root), env={"PATH": str(bindir)})
    assert result.code == 2
    assert "git cannot be run (Permission denied)" in result.err
    assert "Traceback" not in result.err
    assert listing(world.src) == []


def test_a_git_that_lists_no_local_environment_variables_exits_two(tmp_path):
    world = simple(tmp_path, "alpha")
    real = shutil.which("git")
    assert real
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "git"
    script.write_text(
        '#!/bin/sh\n[ "$1 $2" = "rev-parse --local-env-vars" ] && exit 0\n'
        f'exec {shlex.quote(real)} "$@"\n'
    )
    script.chmod(0o755)
    result = world.run("alpha", env={"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"})
    assert result.code == 2
    assert "`git rev-parse --local-env-vars` failed (GIT_DIR is not in its output)" in result.err
    assert listing(world.src) == []


def test_the_failure_of_the_environment_probe_shows_one_line_of_gits_message(tmp_path):
    world = simple(tmp_path, "alpha")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "git"
    script.write_text("#!/bin/sh\necho 'first line' >&2\necho 'second line' >&2\nexit 3\n")
    script.chmod(0o755)
    result = world.run("alpha", env={"PATH": str(bindir)})
    assert result.code == 2
    assert "failed (first line)" in result.err and "second line" not in result.err


def test_missing_git_exits_two(tmp_path):
    world = simple(tmp_path, "alpha")
    result = world.run("alpha", env={"PATH": str(tmp_path / "empty")})
    assert result.code == 2
    assert "git is not installed" in result.err
    assert listing(world.src) == []


def test_the_environment_is_read_only_in_files_registry_and_clone():
    allowed = {"files.py", "registry.py", "clone.py"}
    for path in sorted(PACKAGES.rglob("*.py")) + sorted((REPO / "src").rglob("*.py")):
        if path.name in allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "environb", "getenv"}:
                raise AssertionError((path.name, node.lineno))
            if isinstance(node, ast.ImportFrom) and node.module == "os":
                assert not {a.name for a in node.names} & {"environ", "environb", "getenv"}, path


# configuration, usage and dependency


def test_clone_without_the_clone_table_exits_two(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", "schema = 1\n[links]\n")
    result = repo.run("clone", "alpha")
    assert result.code == 2
    assert "[clone] is absent" in result.err


@pytest.mark.parametrize("args", [(), ("alpha", "beta")])
def test_not_exactly_one_id_is_a_usage_error(tmp_path, args):
    world = simple(tmp_path, "alpha", "beta")
    result = world.run(*args)
    assert result.code == 2
    assert listing(world.src) == []


def test_an_unknown_id_exits_two(tmp_path):
    world = simple(tmp_path, "alpha")
    result = world.run("nothing")
    assert result.code == 2 and "`nothing`" in result.err
    assert listing(world.src) == []


def test_an_alias_collision_that_excludes_an_entry_is_reported_not_called_excluded(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    make_remote(tmp_path, "a")
    make_remote(tmp_path, "b")
    world.configure(
        world.entry("a"),
        world.entry("b") | {"aliases": ["a"]},
        source={"aliases": "aliases", "exclude": ["a"]},
    )
    result = world.run("b")
    assert result.code == 1
    assert "also an id or alias of registry.yaml: repos[0]" in result.out
    assert "excluded" not in result.out + result.err
    assert listing(world.src) == []


@pytest.mark.parametrize("state", ["new", "file"])
def test_an_id_with_an_invisible_character_is_escaped_wherever_it_is_printed(tmp_path, state):
    name = "al\u202epha"
    world = World(tmp_path)
    world.src.mkdir()
    make_remote(tmp_path, "alpha")
    world.configure({"name": name, "url": world.url("alpha")})
    if state == "file":
        (world.src / name).write_text("mine\n")
    result = world.run(name)
    assert result.code == (0 if state == "new" else 1)
    assert "\u202e" not in result.out
    assert "al\\u202epha" in result.out


def test_an_excluded_id_exits_two_saying_it_is_excluded(tmp_path):
    world = simple(tmp_path, "alpha")
    world.configure(world.entry("alpha"), source={"exclude": ["alpha"]})
    result = world.run("alpha")
    assert result.code == 2 and "excluded" in result.err
    assert listing(world.src) == []


def test_declaration_problems_of_the_entry_stop_it_before_any_git_call(tmp_path):
    world = simple(tmp_path, "alpha")
    world.configure(world.entry("alpha", local="/nowhere/alpha"))
    env, log = wrapped_git(tmp_path)
    result = world.run("alpha", env=env)
    assert result.code == 1
    assert result.out.startswith("clone: 1 problem(s)\nregistry.yaml: repos[0] (alpha): declared deviation")
    assert destination_calls(log, world.src / "alpha") == []
    assert listing(world.src) == []


def test_a_problem_in_another_entry_does_not_stop_the_clone(tmp_path):
    world = simple(tmp_path, "alpha")
    world.configure(world.entry("alpha"), {"name": "bad", "url": "/srv/example/bad.git"})
    result = world.run("alpha")
    assert result.code == 0, result.out
    assert (world.src / "alpha" / "README").exists()


def test_check_never_clones(tmp_path):
    world = simple(tmp_path, "alpha")
    result = world.repo.run("check", extra_env={"HOME": str(world.home), "SRC": str(world.src)})
    assert "clone:" not in result.out
    assert listing(world.src) == []


def test_clone_without_pyyaml_exits_two_naming_the_remedy_with_clone(tmp_path):
    # PyYAML is a declared dependency; this is the error path of an environment built another way.
    world = simple(tmp_path, "alpha")
    script = (
        "import runpy, sys\n"
        "sys.modules['yaml'] = None\n"
        "sys.argv = ['mgtk-repo-utils'] + sys.argv[1:]\n"
        "runpy.run_module('mgtk_repo_utils_cli', run_name='__main__')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script, "clone", "alpha"],
        cwd=world.repo.root,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": os.environ["PATH"], "HOME": str(world.home)},
    )
    assert proc.returncode == 2 and proc.stdout == ""
    assert "PyYAML is required" in proc.stderr
    assert "--with pyyaml mgtk-repo-utils clone <id>" in proc.stderr
    assert listing(world.src) == []


# sets (design section 16, revision 6)


def test_a_set_clones_each_entry_in_order_and_prints_each_report(tmp_path):
    world = simple(tmp_path, "alpha", "beta")
    world.configure(world.entry("alpha"), world.entry("beta"), source={"sets": {"all": {}}})
    result = world.run("--all")
    assert result.code == 0
    assert result.out == (
        f"clone: ok (cloned alpha to {world.src / 'alpha'})\n"
        f"clone: ok (cloned beta to {world.src / 'beta'})\n"
    )
    assert (world.src / "alpha" / "README").exists() and (world.src / "beta" / "README").exists()


def test_set_selects_the_entries_whose_condition_matches(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    for name in ("alpha", "beta"):
        make_remote(tmp_path, name)
    world.configure(
        world.entry("alpha", group="one"),
        world.entry("beta", group="two"),
        source={"sets": {"first": {"group": ["one"]}}},
    )
    result = world.run("--set", "first")
    assert result.code == 0
    assert (world.src / "alpha").exists() and not (world.src / "beta").exists()


def test_a_failing_entry_does_not_stop_the_next_and_the_exit_code_is_the_highest(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    make_remote(tmp_path, "beta")  # alpha has no remote, so its `git clone` fails
    world.configure(world.entry("alpha"), world.entry("beta"), source={"sets": {"all": {}}})
    result = world.run("--all")
    assert result.code == 1
    assert "clone: 1 problem(s)" in result.out
    assert f"clone: ok (cloned beta to {world.src / 'beta'})" in result.out
    assert (world.src / "beta" / "README").exists() and not (world.src / "alpha").exists()


def test_an_entry_that_ends_with_an_error_counts_two_and_the_next_is_still_handled(tmp_path):
    world = World(tmp_path)
    world.src.mkdir()
    make_remote(tmp_path, "alpha")
    make_remote(tmp_path, "beta")
    world.configure(
        world.entry("alpha", local="$SRC/missing/alpha"),
        world.entry("beta"),
        source={"sets": {"all": {}}},
    )
    result = world.run("--all")
    assert result.code == 2
    assert "mgtk-repo-utils: clone: the parent of the declared destination" in result.err
    assert (world.src / "beta" / "README").exists()


def test_a_missing_root_is_reported_once_and_creates_nothing(tmp_path):
    world = World(tmp_path)  # `$SRC` is not created
    for name in ("alpha", "beta"):
        make_remote(tmp_path, name)
    world.configure(world.entry("alpha"), world.entry("beta"), source={"sets": {"all": {}}})
    result = world.run("--all")
    assert result.code == 2
    assert result.err.count("mgtk-repo-utils: clone: ") == 1
    assert result.err.count("is not an existing directory") == 1
    assert result.out == "" and not world.src.exists()


def test_a_missing_root_does_not_stop_entries_of_another_root(tmp_path):
    world = World(tmp_path, roots='{ work = "$SRC", more = "$MORE" }')
    world.src.mkdir()
    more = tmp_path / "more"  # not created
    for name in ("alpha", "beta", "gamma"):
        make_remote(tmp_path, name)
    world.configure(
        world.entry("alpha", group="more"),
        world.entry("beta", group="more"),
        world.entry("gamma", group="work"),
        source={
            "root": {"by": "group", "map": {"more": "more", "work": "work"}},
            "sets": {"all": {}},
        },
    )
    result = world.run("--all", env={"MORE": str(more)})
    assert result.code == 2
    assert result.err.count("root `more` is not an existing directory") == 1
    assert (world.src / "gamma" / "README").exists()


def test_a_set_reports_a_present_checkout_as_present(tmp_path):
    world = simple(tmp_path, "alpha", "beta")
    world.configure(world.entry("alpha"), world.entry("beta"), source={"sets": {"all": {}}})
    assert world.run("alpha").code == 0
    result = world.run("--all")
    assert result.code == 0
    assert result.out.splitlines()[0] == f"clone: ok (alpha is present at {world.src / 'alpha'})"


def test_an_undeclared_set_is_a_usage_error_and_all_needs_a_set_named_all(tmp_path):
    world = simple(tmp_path, "alpha")
    world.configure(world.entry("alpha"), source={"sets": {"first": {}}})
    for args in (("--set", "nothing"), ("--all",)):
        result = world.run(*args)
        assert result.code == 2 and result.out == ""
        assert "no source declares the set" in result.err and "`first`" in result.err
    assert listing(world.src) == []


@pytest.mark.parametrize("args", [("alpha", "--set", "all"), ("alpha", "--all"), ("--set", "all", "--all")])
def test_an_id_a_set_and_all_are_exclusive(tmp_path, args):
    world = simple(tmp_path, "alpha")
    world.configure(world.entry("alpha"), source={"sets": {"all": {}}})
    result = world.run(*args)
    assert result.code == 2
    assert listing(world.src) == []
