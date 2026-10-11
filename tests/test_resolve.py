# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys

import pytest

from support import COMMAND, Repo, pinned, toml_value

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
    return "[[clone.sources]]\n" + "".join(f"{k} = {toml_value(v)}\n" for k, v in values.items())


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


# routed roots, sets, --route, --destination-root and --format json (design section 14, revision 6)

BY_CLASS = {"by": "class", "map": {"project": "work", "template": "ops"}}
SETS = {
    "all": {},
    "active": {"status": ["active"]},
    "projects": {"status": ["active"], "class": ["project"]},
}
ROUTED_REGISTRY = (
    "repos:\n"
    "  - {repo: example/alpha, status: active}\n"
    "  - {repo: example/beta, status: archived, class: template}\n"
    "  - {repo: example/gamma, status: active, class: template}\n"
    "  - {repo: example/notes, status: active}\n"
)


def routed_repo(tmp_path, registry=ROUTED_REGISTRY, *extra: str, **keys):
    spec = source(
        name="projects", root=BY_CLASS, defaults={"class": "project"}, sets=SETS, **keys
    )
    return make_repo(tmp_path, registry, config_text(spec, *extra))


def lines(out: str) -> list[list[str]]:
    return [line.split("\t") for line in out.splitlines()]


def test_set_prints_one_line_per_entry_in_source_then_entry_order(tmp_path):
    code, out, err = run_in(routed_repo(tmp_path), ENV, "resolve", "--set", "active")
    assert (code, err) == (0, "")
    assert lines(out) == [
        ["alpha", "/home/user/src/alpha", "git@example.com:example/alpha.git"],
        ["gamma", "/data/ops/gamma", "git@example.com:example/gamma.git"],
    ]


def test_all_is_the_set_named_all(tmp_path):
    repo = routed_repo(tmp_path)
    assert run_in(repo, ENV, "resolve", "--all") == run_in(repo, ENV, "resolve", "--set", "all")
    assert [row[0] for row in lines(run_in(repo, ENV, "resolve", "--all")[1])] == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_excluded_entries_are_absent_from_a_set(tmp_path):
    out = run_in(routed_repo(tmp_path), ENV, "resolve", "--all")[1]
    assert "notes" not in out


def test_a_set_declared_by_two_sources_lists_the_first_sources_entries_first(tmp_path):
    extra = source(
        name="more", file="other.yaml", entries="more[]", sets={"all": {}}, exclude=[]
    )
    repo = routed_repo(tmp_path, ROUTED_REGISTRY, extra)
    repo.write("other.yaml", "more:\n  - repo: example/delta\n")
    code, out, _ = run_in(repo, ENV, "resolve", "--all")
    assert code == 0
    assert [row[0] for row in lines(out)] == ["alpha", "beta", "gamma", "delta"]


def test_an_undeclared_set_is_a_usage_error_naming_the_declared_sets(tmp_path):
    code, out, err = run_in(routed_repo(tmp_path), ENV, "resolve", "--set", "nothing")
    assert (code, out) == (2, "")
    assert "no source declares the set `nothing`" in err
    assert "`all`, `active`, `projects`" in err


def test_all_without_a_set_named_all_is_an_undeclared_set(tmp_path):
    repo = make_repo(tmp_path, config=config_text(source(sets={"active": {}})))
    code, out, err = run_in(repo, ENV, "resolve", "--all")
    assert (code, out) == (2, "")
    assert "no source declares the set `all`" in err and "`active`" in err


def test_a_config_with_no_sets_names_none(tmp_path):
    code, _, err = run_in(make_repo(tmp_path), ENV, "resolve", "--all")
    assert code == 2 and "declared sets are none" in err


def test_a_set_prints_the_other_entries_when_one_has_a_problem_and_exits_one(tmp_path):
    registry = ROUTED_REGISTRY + "  - {repo: example/delta, status: active, class: other}\n"
    code, out, err = run_in(routed_repo(tmp_path, registry), ENV, "resolve", "--set", "active")
    assert code == 1
    assert [row[0] for row in lines(out)] == ["alpha", "gamma"]
    assert "(delta)" in err and "`root.map` does not list" in err


def test_a_routed_entry_with_a_problem_exits_one_for_its_id(tmp_path):
    registry = "repos:\n  - {repo: example/delta, class: other}\n"
    code, out, err = run_in(routed_repo(tmp_path, registry), ENV, "resolve", "delta")
    assert (code, out) == (1, "")
    assert "`root.map` does not list" in err


def test_set_and_id_together_are_a_usage_error(tmp_path):
    repo = routed_repo(tmp_path)
    for args in (("alpha", "--set", "all"), ("--set", "all", "--all"), ("--all", "--check")):
        code, out, err = run_in(repo, ENV, "resolve", *args)
        assert (code, out) == (2, "")
        assert "usage: mgtk-repo-utils resolve" in err


# --route


def route(repo, *args, env=ENV):
    return run_in(repo, env, "resolve", "--route", "projects", *args)


def test_route_prints_the_line_of_an_entry_the_registry_does_not_hold(tmp_path):
    code, out, err = route(routed_repo(tmp_path), "repo=example/new", "class=template")
    assert (code, err) == (0, "")
    assert out == "new\t/data/ops/new\tgit@example.com:example/new.git\n"


def test_route_chooses_the_root_by_defaults_when_the_field_is_not_given(tmp_path):
    out = route(routed_repo(tmp_path), "repo=example/new")[1]
    assert out == "new\t/home/user/src/new\tgit@example.com:example/new.git\n"


def test_route_reports_an_id_the_registry_holds_and_prints_nothing(tmp_path):
    code, out, err = route(routed_repo(tmp_path), "repo=example/alpha")
    assert (code, out) == (1, "")
    assert "also an id or alias of registry.yaml: repos[0]" in err


def test_route_reports_a_destination_inside_an_existing_one(tmp_path):
    repo = routed_repo(tmp_path, local="local")
    repo.write("registry.yaml", "repos:\n  - {repo: example/alpha, local: ~/src/deep}\n")
    code, out, err = route(repo, "repo=example/new", "local=~/src/deep/inner")
    assert (code, out) == (1, "")
    assert "equals, contains or lies inside" in err


def test_route_checks_a_given_local(tmp_path):
    repo = routed_repo(tmp_path, local="local")
    outside = route(repo, "repo=example/new", "local=/elsewhere/new")
    default = route(repo, "repo=example/new", "local=~/src/new")
    declared = route(repo, "repo=example/new", "local=~/src/odd")
    assert outside[0] == default[0] == 1 and outside[1] == default[1] == ""
    assert "outside every root" in outside[2] and "equals the default destination" in default[2]
    assert declared[:2] == (0, "new\t/home/user/src/odd\tgit@example.com:example/new.git\n")


def test_route_reports_a_value_the_map_does_not_list(tmp_path):
    code, out, err = route(routed_repo(tmp_path), "repo=example/new", "class=other")
    assert (code, out) == (1, "")
    assert "`class` is `other`" in err


def test_route_into_a_source_without_a_name_is_a_usage_error_naming_the_known_names(tmp_path):
    repo = make_repo(tmp_path)
    code, out, err = run_in(repo, ENV, "resolve", "--route", "clone.sources[0]", "repo=x/y")
    assert (code, out) == (2, "")
    assert "the named sources are none" in err


def test_route_into_an_unknown_source_names_the_known_names(tmp_path):
    code, out, err = run_in(
        routed_repo(tmp_path), ENV, "resolve", "--route", "other", "repo=example/new"
    )
    assert (code, out) == (2, "")
    assert "no source is named `other`" in err and "`projects`" in err


@pytest.mark.parametrize("field", ["repo", "=x"])
def test_route_with_a_field_that_is_not_key_equals_value_is_a_usage_error(tmp_path, field):
    code, out, err = route(routed_repo(tmp_path), "repo=example/new", field)
    assert (code, out) == (2, "")
    assert "<key>=<value>" in err


def test_route_with_only_a_source_builds_an_entry_with_no_fields_and_reports_it(tmp_path):
    code, out, err = route(routed_repo(tmp_path))
    assert (code, out) == (1, "")
    assert "`repo` must be a non-empty string" in err


def test_route_writes_nothing(tmp_path):
    repo = routed_repo(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))
    assert route(repo, "repo=example/new")[0] == 0
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


# --destination-root


def test_root_prints_the_expanded_root_without_a_trailing_slash(tmp_path):
    repo = make_repo(tmp_path)
    assert run_in(repo, ENV, "resolve", "--destination-root", "ops") == (0, "/data/ops\n", "")
    assert run_in(repo, ENV, "resolve", "--destination-root", "work") == (0, "/home/user/src\n", "")


def test_root_expands_only_the_named_root(tmp_path):
    code, out, _ = run_in(make_repo(tmp_path), {"HOME": "/home/user"}, "resolve", "--destination-root", "work")
    assert (code, out) == (0, "/home/user/src\n")


def test_root_with_an_unset_variable_exits_two_with_nothing_on_standard_output(tmp_path):
    code, out, err = run_in(make_repo(tmp_path), {"HOME": "/home/user"}, "resolve", "--destination-root", "ops")
    assert (code, out) == (2, "")
    assert "`OPS_ROOT`" in err and "root `ops`" in err


def test_root_with_an_unknown_name_is_a_usage_error_naming_the_declared_roots(tmp_path):
    code, out, err = run_in(make_repo(tmp_path), ENV, "resolve", "--destination-root", "nothing")
    assert (code, out) == (2, "")
    assert "no root is named `nothing`" in err and "`work`, `ops`" in err


def test_the_common_root_option_is_still_the_repository_root(tmp_path):
    repo = make_repo(tmp_path)
    code, out, _ = run_in(repo, ENV, "resolve", "alpha", "--root", str(repo.root))
    assert code == 0 and out.startswith("alpha\t")


# --format json


def objects(out: str) -> list[dict]:
    return json.loads(out)


def test_json_for_an_id_is_an_array_of_one_object_with_the_documented_fields(tmp_path):
    code, out, err = run_in(routed_repo(tmp_path), ENV, "resolve", "gamma", "--format", "json")
    assert (code, err) == (0, "")
    assert objects(out) == [
        {
            "id": "gamma",
            "destination": "/data/ops/gamma",
            "url": "git@example.com:example/gamma.git",
            "root": "ops",
            "source": "projects",
            "dir": "gamma",
            "deviation": False,
        }
    ]


def test_json_names_an_unnamed_source_by_its_position_and_marks_a_deviation(tmp_path):
    code, out, _ = run_in(make_repo(tmp_path), ENV, "resolve", "gamma", "--format", "json")
    assert code == 0
    (obj,) = objects(out)
    assert (obj["source"], obj["deviation"], obj["root"]) == ("clone.sources[0]", True, "work")
    assert obj["destination"] == "/home/user/src/odd name"


def test_json_for_a_set_lists_the_entries_in_the_order_of_the_text_lines(tmp_path):
    repo = routed_repo(tmp_path)
    text = run_in(repo, ENV, "resolve", "--all")[1]
    code, out, _ = run_in(repo, ENV, "resolve", "--all", "--format", "json")
    assert code == 0
    assert [(o["id"], o["destination"], o["url"]) for o in objects(out)] == [
        tuple(row) for row in lines(text)
    ]


def test_json_for_route_is_an_array_of_one_object(tmp_path):
    code, out, _ = route(routed_repo(tmp_path), "repo=example/new", "class=template", "--format", "json")
    assert code == 0
    (obj,) = objects(out)
    assert (obj["id"], obj["root"], obj["destination"], obj["source"]) == (
        "new",
        "ops",
        "/data/ops/new",
        "projects",
    )


def test_json_for_root_is_one_object(tmp_path):
    code, out, _ = run_in(make_repo(tmp_path), ENV, "resolve", "--destination-root", "ops", "--format", "json")
    assert code == 0
    assert json.loads(out) == {"root": "ops", "path": "/data/ops"}


def test_json_prints_nothing_on_standard_output_when_an_entry_has_a_problem(tmp_path):
    registry = ROUTED_REGISTRY + "  - {repo: example/delta, class: other}\n"
    repo = routed_repo(tmp_path, registry)
    code, out, err = run_in(repo, ENV, "resolve", "--set", "all", "--format", "json")
    assert (code, out) == (1, "")
    assert "(delta)" in err


@pytest.mark.parametrize(
    "args",
    [
        ("nothing",),
        ("--set", "nothing"),
        ("--route", "projects", "repo"),
        ("--destination-root", "nothing"),
        ("--route", "projects", "repo=example/alpha"),
    ],
)
def test_json_prints_nothing_on_standard_output_on_any_non_zero_exit(tmp_path, args):
    code, out, err = run_in(routed_repo(tmp_path), ENV, "resolve", *args, "--format", "json")
    assert code != 0 and out == ""
    assert err != ""


def test_json_with_an_unset_variable_exits_two_with_nothing_on_standard_output(tmp_path):
    code, out, _ = run_in(
        routed_repo(tmp_path), {"HOME": "/home/user"}, "resolve", "--set", "all", "--format", "json"
    )
    assert (code, out) == (2, "")


def test_json_does_not_apply_to_check(tmp_path):
    code, out, err = run_in(make_repo(tmp_path), ENV, "resolve", "--check", "--format", "json")
    assert (code, out) == (2, "")
    assert "--format" in err


def test_the_default_format_is_text(tmp_path):
    repo = make_repo(tmp_path)
    assert run_in(repo, ENV, "resolve", "alpha") == run_in(repo, ENV, "resolve", "alpha", "--format", "text")
