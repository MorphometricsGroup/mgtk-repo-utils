# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys

import pytest

from support import COMMAND, Repo, pinned

ROOTS = '{ work = "~/src", ops = "$OPS_ROOT" }'
URLS = ["git@example.com:example/*", "git@example.com:example-org/*"]
REGISTRY = (
    "repos:\n"
    "  - repo: example/alpha\n"
    "  - repo: example-org/beta\n"
    "  - repo: example/gamma\n"
    "    local: ~/src/odd name\n"
    "  - repo: example/notes\n"
)


def config_text(*sources: str, roots: str = ROOTS, lang: str = "en") -> str:
    return (
        f'schema = 1\nlang = "{lang}"\n[clone]\nroots = {roots}\nurls = {json.dumps(URLS)}\n'
        + "".join(sources)
    )


def source(**keys: object) -> str:
    values = {
        "file": "registry.yaml",
        "entries": "repos[]",
        "root": "work",
        "url": "git@example.com:{repo}.git",
        "local": "local",
        "exclude": ["notes"],
    } | keys
    return "[[clone.sources]]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in values.items())


def make_repo(tmp_path, registry: str = REGISTRY, config: str | None = None) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", config or config_text(source()))
    repo.write("registry.yaml", registry)
    return repo


def run_in(repo: Repo, env: dict[str, str], *args: str):
    """Run with exactly `env` (plus the bytecode switch), so a variable can be left unset."""
    proc = subprocess.run(
        [*COMMAND, *args],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"} | env,
    )
    return proc.returncode, proc.stdout, proc.stderr


ENV = {"HOME": "/home/user", "OPS_ROOT": "/data/ops/"}


# resolve <id>


def test_resolve_prints_id_destination_and_url_separated_by_tabs(tmp_path):
    repo = make_repo(tmp_path)
    code, out, err = run_in(repo, ENV, "resolve", "alpha")
    assert (code, err) == (0, "")
    assert out == "alpha\t/home/user/src/alpha\tgit@example.com:example/alpha.git\n"


def test_resolve_prints_a_declared_deviation_as_the_destination(tmp_path):
    repo = make_repo(tmp_path)
    code, out, _ = run_in(repo, ENV, "resolve", "gamma")
    assert code == 0
    assert out == "gamma\t/home/user/src/odd name\tgit@example.com:example/gamma.git\n"


def test_an_alias_resolves_to_the_entrys_id(tmp_path):
    spec = source(id="name", aliases="aliases", url="{url}", exclude=[])
    registry = "repos:\n  - {name: alpha, aliases: [first], url: 'git@example.com:example/a.git'}\n"
    repo = make_repo(tmp_path, registry, config_text(spec))
    code, out, _ = run_in(repo, ENV, "resolve", "first")
    assert code == 0
    assert out == "alpha\t/home/user/src/alpha\tgit@example.com:example/a.git\n"


def test_a_root_variable_with_a_trailing_slash_gives_no_double_slash(tmp_path):
    repo = make_repo(tmp_path, config=config_text(source(root="ops")))
    code, out, _ = run_in(repo, ENV, "resolve", "alpha")
    assert code == 0
    assert out.split("\t")[1] == "/data/ops/alpha"


def test_an_unset_variable_of_another_entrys_root_does_not_matter(tmp_path):
    config = config_text(
        source(exclude=[]),
        source(file="other.yaml", entries="more[]", root="ops", exclude=[]),
    )
    repo = make_repo(tmp_path, config=config)
    repo.write("other.yaml", "more:\n  - repo: example/delta\n")
    code, out, _ = run_in(repo, {"HOME": "/home/user"}, "resolve", "alpha")
    assert code == 0, out
    assert out.startswith("alpha\t/home/user/src/alpha\t")


@pytest.mark.parametrize("value", [None, "", "relative/path", "/a\tb"])
def test_an_unset_empty_or_relative_variable_of_this_entrys_root_exits_two(tmp_path, value):
    repo = make_repo(tmp_path, config=config_text(source(root="ops")))
    env = {"HOME": "/home/user"} | ({} if value is None else {"OPS_ROOT": value})
    code, out, err = run_in(repo, env, "resolve", "alpha")
    assert code == 2
    assert out == ""
    assert "`OPS_ROOT`" in err and "root `ops`" in err


def test_an_unset_home_exits_two_for_a_tilde_root(tmp_path):
    repo = make_repo(tmp_path)
    code, out, err = run_in(repo, {"OPS_ROOT": "/data/ops"}, "resolve", "alpha")
    assert code == 2
    assert "`HOME` is unset or empty" in err and "root `work`" in err


def test_a_relative_home_exits_two(tmp_path):
    repo = make_repo(tmp_path)
    code, _, err = run_in(repo, {"HOME": "home/user"}, "resolve", "alpha")
    assert code == 2
    assert "`HOME` is `home/user`" in err


def test_an_unknown_id_exits_two_and_names_it(tmp_path):
    code, out, err = run_in(make_repo(tmp_path), ENV, "resolve", "nothing")
    assert code == 2
    assert out == ""
    assert "`nothing`" in err and "no entry" in err


def test_an_excluded_id_exits_two_saying_it_is_excluded(tmp_path):
    code, out, err = run_in(make_repo(tmp_path), ENV, "resolve", "notes")
    assert code == 2
    assert out == ""
    assert "`notes` is excluded" in err and "unknown" not in err


def test_an_entry_with_an_attached_problem_exits_one_on_standard_error(tmp_path):
    registry = "repos:\n  - repo: example/alpha\n    local: /nowhere/alpha\n"
    code, out, err = run_in(make_repo(tmp_path, registry), ENV, "resolve", "alpha")
    assert code == 1
    assert out == ""
    assert err.startswith("registry.yaml: repos[0] (alpha): declared deviation `/nowhere/alpha`")


def test_a_problem_in_another_entry_does_not_stop_resolve(tmp_path):
    registry = (
        "repos:\n  - repo: example/alpha\n  - repo: someone-else/bad\n  - 5\n"
    )
    repo = make_repo(tmp_path, registry, config_text(source(exclude=["ghost"])))
    assert run_in(repo, ENV, "resolve", "--check")[0] == 1
    code, out, err = run_in(repo, ENV, "resolve", "alpha")
    assert (code, err) == (0, "")
    assert out.startswith("alpha\t")
    assert run_in(repo, ENV, "resolve", "bad")[0] == 1


def test_a_colliding_id_attaches_to_both_entries(tmp_path):
    registry = "repos:\n  - repo: example/a\n  - repo: example-org/a\n"
    code, _, err = run_in(make_repo(tmp_path, registry), ENV, "resolve", "a")
    assert code == 1
    assert "also an id or alias of registry.yaml: repos[0]" in err


@pytest.mark.parametrize(
    "args",
    [(), ("a", "b"), ("a", "--check"), ("--check", "b")],
)
def test_usage_errors_exit_two(tmp_path, args):
    code, out, err = run_in(make_repo(tmp_path), ENV, "resolve", *args)
    assert code == 2
    assert out == ""
    assert "usage: mgtk-repo-utils resolve" in err


def test_resolve_without_a_clone_table_exits_two(tmp_path):
    repo = make_repo(tmp_path, config="schema = 1\n")
    code, _, err = run_in(repo, ENV, "resolve", "--check")
    assert code == 2
    assert "[clone] is absent" in err


def test_resolve_writes_nothing_and_does_not_look_at_the_destination(tmp_path):
    repo = make_repo(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    home = tmp_path / "home"  # does not exist
    assert run_in(repo, {"HOME": str(home)}, "resolve", "alpha")[0] == 0
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
    assert not home.exists()


# resolve --check


def test_check_reports_ok_with_counts(tmp_path):
    code, out, err = run_in(make_repo(tmp_path), ENV, "resolve", "--check")
    assert (code, err) == (0, "")
    assert out == "resolve: ok (4 entr(ies) from 1 source(s), 1 excluded)\n"


def test_check_reports_in_japanese_when_configured(tmp_path):
    repo = make_repo(tmp_path, config=config_text(source(), lang="ja"))
    code, out, _ = run_in(repo, ENV, "resolve", "--check")
    assert code == 0
    assert out == "resolve: ok（1 件のソースからエントリ 4 件，うち除外 1 件）\n"


def test_check_exits_one_with_a_header_and_one_line_per_problem(tmp_path):
    registry = "repos:\n  - repo: someone-else/a\n  - repo: example/b\n    local: /x\n"
    code, out, err = run_in(make_repo(tmp_path, registry), ENV, "resolve", "--check")
    assert code == 1
    assert err == ""
    lines = out.splitlines()
    assert lines[0] == "resolve: 3 problem(s)"  # two entries, and `notes` matches nothing
    assert any(line.startswith("mgtk-repo-utils.toml: clone.sources[0]: `exclude` lists `notes`") for line in lines)
    assert any(line.startswith("registry.yaml: repos[0] (a): URL ") for line in lines)
    assert any(line.startswith("registry.yaml: repos[1] (b): declared deviation ") for line in lines)
    assert not any(line.startswith("resolve: ok") for line in lines)


def test_the_check_report_is_the_same_under_an_empty_environment(tmp_path):
    registry = REGISTRY + "  - repo: someone-else/bad\n"
    repo = make_repo(tmp_path, registry)
    with_env = run_in(repo, ENV, "resolve", "--check", "--root", str(repo.root))
    without = run_in(repo, {}, "resolve", "--check", "--root", str(repo.root))
    assert with_env == without
    assert without[0] == 1
    assert "`HOME`" not in without[1] + without[2]


def test_check_reads_the_working_tree_not_the_index(tmp_path):
    repo = make_repo(tmp_path)
    repo.stage()
    repo.write("registry.yaml", "repos:\n  - repo: someone-else/bad\n")
    assert run_in(repo, ENV, "resolve", "--check")[0] == 1


def test_a_missing_registry_exits_two_on_standard_error(tmp_path):
    repo = make_repo(tmp_path)
    (repo.root / "registry.yaml").unlink()
    code, out, err = run_in(repo, ENV, "resolve", "--check")
    assert code == 2 and out == ""
    assert "registry.yaml: cannot read the registry" in err


def test_a_non_mapping_registry_exits_two(tmp_path):
    code, _, err = run_in(make_repo(tmp_path, ""), ENV, "resolve", "--check")
    assert code == 2
    assert "the top level must be a mapping" in err


@pytest.mark.parametrize("date", ["2024-02-30", "2024-13-01"])
def test_an_impossible_yaml_date_exits_two_without_a_traceback(tmp_path, date):
    registry = f"repos:\n  - repo: example/alpha\n    created: {date}\n"
    code, out, err = run_in(make_repo(tmp_path, registry), ENV, "resolve", "--check")
    assert code == 2 and out == ""
    assert "registry.yaml: invalid YAML (" in err
    assert "Traceback" not in err


def test_an_alias_collision_that_excludes_an_entry_is_reported_not_called_excluded(tmp_path):
    spec = source(id="name", aliases="aliases", url="{url}", exclude=["a"])
    registry = (
        "repos:\n"
        "  - {name: a, url: 'git@example.com:example/a.git'}\n"
        "  - {name: b, aliases: [a], url: 'git@example.com:example/b.git'}\n"
    )
    repo = make_repo(tmp_path, registry, config_text(spec))
    code, out, err = run_in(repo, ENV, "resolve", "b")
    assert code == 1 and out == ""
    assert "also an id or alias of registry.yaml: repos[0]" in err
    assert "excluded" not in err


def test_a_home_with_a_c1_control_character_exits_two_for_a_tilde_root(tmp_path):
    code, out, err = run_in(make_repo(tmp_path), {"HOME": "/home/us\u0085er"}, "resolve", "alpha")
    assert code == 2 and out == ""
    assert "`HOME` is `" in err and "\\x85" in err


# check


def checked(tmp_path, config: str, registry: str = REGISTRY):
    repo = pinned(Repo(tmp_path / "repo"))
    repo.write("mgtk-repo-utils.toml", config)
    repo.write("registry.yaml", registry)
    repo.write("README.md", "ok\n")
    repo.stage()
    return repo


def headers(out: str) -> list[str]:
    return [
        line.split(":")[0]
        for line in out.splitlines()
        if line.startswith(("freeze-lint:", "link-check:", "resolve:"))
    ]


def test_check_runs_resolve_after_link_check(tmp_path):
    repo = checked(tmp_path, config_text(source()) + "[links]\n")
    code, out, err = run_in(repo, ENV, "check")
    assert (code, err) == (0, "")
    assert headers(out) == ["link-check", "resolve"]


def test_check_fails_when_the_static_check_fails(tmp_path):
    repo = checked(tmp_path, config_text(source(exclude=[])), "repos:\n  - repo: someone-else/a\n")
    code, out, _ = run_in(repo, ENV, "check")
    assert code == 1
    assert headers(out) == ["resolve"]
    assert "resolve: 1 problem(s)" in out


def test_check_exits_two_for_a_missing_registry(tmp_path):
    repo = checked(tmp_path, config_text(source()))
    (repo.root / "registry.yaml").unlink()
    code, out, err = run_in(repo, ENV, "check")
    assert code == 2
    assert "cannot read the registry" in err
    assert headers(out) == []


def test_check_without_a_clone_table_does_not_run_resolve(tmp_path):
    repo = checked(tmp_path, "schema = 1\n[links]\n")
    code, out, _ = run_in(repo, ENV, "check")
    assert code == 0
    assert headers(out) == ["link-check"]


def test_check_reports_each_step_in_order_and_names_the_step_that_failed(tmp_path):
    repo = checked(tmp_path, config_text(source()) + "[links]\n")
    (repo.root / "registry.yaml").unlink()
    proc = subprocess.run(
        [*COMMAND, "check"],
        cwd=repo.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"} | ENV,
    )
    assert proc.returncode == 2
    link, error = (
        proc.stdout.index(text) for text in ("link-check: ok", "mgtk-repo-utils: resolve: ")
    )
    assert link < error


def test_check_exits_two_for_an_impossible_yaml_date_without_a_traceback(tmp_path):
    registry = "repos:\n  - repo: example/alpha\n    created: 2024-02-30\n"
    repo = checked(tmp_path, config_text(source()) + "[links]\n", registry)
    code, out, err = run_in(repo, ENV, "check")
    assert code == 2
    assert "mgtk-repo-utils: resolve: registry.yaml: invalid YAML" in err and "Traceback" not in err
    assert headers(out) == ["link-check"]


# dependency: PyYAML hidden (a declared dependency; the error path of an environment built another way)


def run_without_yaml(repo: Repo, *args: str):
    script = (
        "import runpy, sys\n"
        "sys.modules['yaml'] = None\n"
        "sys.argv = ['mgtk-repo-utils'] + sys.argv[1:]\n"
        "runpy.run_module('mgtk_repo_utils_cli', run_name='__main__')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"} | ENV,
    )
    return proc.returncode, proc.stdout, proc.stderr


REMEDY = "--with pyyaml mgtk-repo-utils resolve --check"


def test_resolve_without_pyyaml_exits_two_naming_the_remedy(tmp_path):
    repo = checked(tmp_path, config_text(source()))
    for args in (("resolve", "--check"), ("resolve", "alpha")):
        code, out, err = run_without_yaml(repo, *args)
        assert code == 2 and out == ""
        assert "PyYAML is required" in err and REMEDY in err


def test_check_without_pyyaml_exits_two_but_still_prints_the_other_reports(tmp_path):
    repo = checked(tmp_path, config_text(source()) + "[links]\n")
    code, out, err = run_without_yaml(repo, "check")
    assert code == 2
    assert "mgtk-repo-utils check`" in err and REMEDY not in err
    assert "mgtk-repo-utils: resolve: " in err
    assert headers(out) == ["link-check"]


def test_check_without_pyyaml_runs_the_tools_that_need_none_and_pin_names_the_gap(tmp_path):
    repo = checked(tmp_path, "schema = 1\n[links]\n")
    code, out, err = run_without_yaml(repo, "check")
    assert code == 2
    assert headers(out) == ["link-check"] and "link-check: ok" in out
    assert "mgtk-repo-utils: pin: PyYAML is required to read .pre-commit-config.yaml" in err


def test_other_tools_run_without_pyyaml_even_with_a_clone_table(tmp_path):
    repo = checked(tmp_path, config_text(source()) + "[links]\n")
    code, out, err = run_without_yaml(repo, "link-check")
    assert (code, err) == (0, "")
    assert out.startswith("link-check: ok")
