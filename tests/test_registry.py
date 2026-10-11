# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest

from mgtk_repo_utils_clone import registry
from mgtk_repo_utils.config import load as load_config
from mgtk_repo_utils.report import ToolError
from support import toml_value

ROOTS = '{ work = "~/src", ops = "~/src/ops" }'
URLS = ["git@example.com:example/*", "git@example.com:example-org/*", "/srv/**", "host:*"]


def source(**keys: object) -> str:
    values = {
        "file": "registry.yaml",
        "entries": "repos[]",
        "root": "work",
        "url": "git@example.com:{repo}.git",
    } | keys
    return "[[clone.sources]]\n" + "".join(f"{k} = {toml_value(v)}\n" for k, v in values.items())


def configure(tmp_path: Path, text: str | None, *sources: str, roots: str = ROOTS, lang: str = "en"):
    if text is not None:
        (tmp_path / "registry.yaml").write_text(text, encoding="utf-8")
    toml = (
        f'schema = 1\nlang = "{lang}"\n[clone]\nroots = {roots}\nurls = {json.dumps(URLS)}\n'
        + "".join(sources or (source(),))
    )
    (tmp_path / "mgtk-repo-utils.toml").write_text(toml, encoding="utf-8")
    return load_config(tmp_path / "mgtk-repo-utils.toml", tmp_path)


def resolved(tmp_path: Path, text: str | None, *sources: str, **kwargs):
    return registry.load(configure(tmp_path, text, *sources, **kwargs))


def rendered(resolution) -> list[str]:
    return sorted(p.render() for p in resolution.problems)


def only(resolution, fragment: str) -> str:
    matching = [line for line in rendered(resolution) if fragment in line]
    assert len(matching) == 1, rendered(resolution)
    return matching[0]


def slugs(*repos: str) -> str:
    return "repos:\n" + "".join(f"  - repo: {repo}\n" for repo in repos)


# archetypes


def test_slug_source_takes_id_and_directory_from_the_url_basename(tmp_path):
    res = resolved(tmp_path, slugs("example/alpha", "example-org/beta"))
    assert rendered(res) == []
    first, second = res.entries
    assert (first.id, first.dir, first.url) == ("alpha", "alpha", "git@example.com:example/alpha.git")
    assert first.position == "repos[0]"
    assert first.destination == "~/src/alpha"
    assert (second.id, second.destination) == ("beta", "~/src/beta")


def test_named_source_with_aliases_and_directory_from_the_url(tmp_path):
    text = (
        "projects:\n"
        "  - name: alpha\n    aliases: [a, first]\n    url: git@example.com:example/alpha-repo.git\n"
        "  - name: beta\n    url: git@example.com:example/beta-repo.git\n"
    )
    spec = source(entries="projects[]", url="{url}", id="name", aliases="aliases", dir="url")
    res = resolved(tmp_path, text, spec)
    assert rendered(res) == []
    alpha, beta = res.entries
    assert (alpha.id, alpha.aliases, alpha.dir) == ("alpha", ("a", "first"), "alpha-repo")
    assert alpha.destination == "~/src/alpha-repo"
    assert beta.aliases == ()
    assert res.find("first") is alpha and res.find("alpha") is alpha
    assert res.find("nothing") is None


def test_a_declared_deviation_is_the_destination_in_the_longest_matching_root(tmp_path):
    text = "repos:\n  - repo: example/alpha\n    local: ~/src/ops/elsewhere\n"
    res = resolved(tmp_path, text, source(local="local"))
    assert rendered(res) == []
    entry = res.entries[0]
    assert (entry.deviation, entry.destination, entry.root) == (
        "~/src/ops/elsewhere",
        "~/src/ops/elsewhere",
        "ops",
    )


def test_a_null_deviation_means_none(tmp_path):
    res = resolved(tmp_path, "repos:\n  - repo: example/alpha\n    local:\n", source(local="local"))
    assert rendered(res) == []
    assert res.entries[0].deviation is None
    assert res.entries[0].root == "work"


def test_several_sources_over_one_file_read_it_once(tmp_path, monkeypatch):
    import yaml

    calls = []
    real = yaml.safe_load
    monkeypatch.setattr(yaml, "safe_load", lambda data: calls.append(1) or real(data))
    text = "repos:\n  - repo: example/a\nother:\n  - repo: example/b\n"
    res = resolved(tmp_path, text, source(), source(entries="other[]"))
    assert rendered(res) == []
    assert len(res.entries) == 2
    assert len(calls) == 1


# walking entries


def test_absent_null_and_empty_branches_and_null_items_yield_nothing(tmp_path):
    text = (
        "teams:\n"
        "  - name: no services\n"
        "  - services:\n"
        "  - services: []\n"
        "  -\n"
        "  - services:\n"
        "      - repo: example/a\n"
        "      -\n"
    )
    res = resolved(tmp_path, text, source(entries="teams[].services[]"))
    assert rendered(res) == []
    assert [e.position for e in res.entries] == ["teams[4].services[0]"]


def test_a_key_that_is_null_at_the_top_yields_a_source_problem_not_an_error(tmp_path):
    res = resolved(tmp_path, "repos:\nother: 1\n")
    assert rendered(res) == [
        "mgtk-repo-utils.toml: clone.sources[0]: no entry in `registry.yaml` at `entries = repos[]`; "
        "an empty result looks like a misspelt key, so fix `entries`, or remove the source "
        "until it has entries"
    ]


@pytest.mark.parametrize(
    "text, entries, path, fragment",
    [
        ("repos: text\n", "repos[]", "registry.yaml: repos", "needs a list, but the value is a string"),
        ("repos:\n  a: 1\n", "repos[]", "registry.yaml: repos", "the value is a mapping"),
        ("teams:\n  - 1\n", "teams[].services[]", "registry.yaml: teams[0]", "looked up in a number"),
        ("repos:\n  - 1\n  - repo: example/a\n", "repos[]", "registry.yaml: repos[0]", "a number, not a mapping"),
        ("repos: 5\n", "repos", "registry.yaml: repos", "a number, not a mapping"),
        ("repos:\n  - [a]\n", "repos[].x", "registry.yaml: repos[0]", "looked up in a list"),
    ],
)
def test_walk_errors_name_the_position(tmp_path, text, entries, path, fragment):
    res = resolved(tmp_path, text, source(entries=entries))
    line = only(res, path + ": ")
    assert fragment in line
    assert line.startswith(path + ": ")


def test_a_final_mapping_reached_without_a_list_is_one_entry(tmp_path):
    res = resolved(tmp_path, "main:\n  repo: example/a\n", source(entries="main"))
    assert rendered(res) == []
    assert res.entries[0].position == "main"


def test_a_source_with_a_walk_error_is_not_also_reported_empty(tmp_path):
    res = resolved(tmp_path, "repos: text\n")
    assert [p.msg_id for p in res.problems] == ["walk-list"]


def test_an_empty_list_alone_is_a_source_problem(tmp_path):
    res = resolved(tmp_path, "repos: []\n")
    assert "clone.sources[0]" in only(res, "no entry in")


def test_a_source_that_is_all_excluded_still_yields_entries(tmp_path):
    res = resolved(tmp_path, slugs("example/a"), source(exclude=["a"]))
    assert rendered(res) == []
    assert res.entries[0].excluded


# registry files (configuration errors)


def test_a_missing_registry_file_is_a_configuration_error(tmp_path):
    with pytest.raises(ToolError, match=r"registry\.yaml: cannot read the registry"):
        resolved(tmp_path, None)


def test_a_registry_that_is_a_directory_is_a_configuration_error(tmp_path):
    (tmp_path / "registry.yaml").mkdir()
    with pytest.raises(ToolError, match="cannot read the registry"):
        resolved(tmp_path, None)


def test_a_yaml_error_names_the_line(tmp_path):
    with pytest.raises(ToolError, match=r"registry\.yaml: invalid YAML at line 2 "):
        resolved(tmp_path, "repos:\n\t- repo: a\n")


@pytest.mark.parametrize("date", ["2024-02-30", "2024-13-01"])
def test_an_impossible_yaml_date_is_a_configuration_error(tmp_path, date):
    with pytest.raises(ToolError, match=r"registry\.yaml: invalid YAML \(.+\); fix the syntax"):
        resolved(tmp_path, f"repos:\n  - repo: example/a\n    created: {date}\n")


def test_nesting_too_deep_for_the_parser_is_a_configuration_error(tmp_path):
    with pytest.raises(ToolError, match=r"registry\.yaml: invalid YAML"):
        resolved(tmp_path, "repos: " + "[" * 5000 + "]" * 5000 + "\n")


@pytest.mark.parametrize("text", ["", "# only a comment\n", "- a\n- b\n", "plain text\n"])
def test_a_registry_whose_top_level_is_not_a_mapping_is_a_configuration_error(tmp_path, text):
    with pytest.raises(ToolError, match="the top level must be a mapping"):
        resolved(tmp_path, text)


def test_configuration_errors_follow_the_configured_language(tmp_path):
    with pytest.raises(ToolError, match="トップレベルはマッピング"):
        resolved(tmp_path, "", lang="ja")


# URL basenames


@pytest.mark.parametrize(
    "url, expected",
    [
        ("git@example.com:example/x.git", "x"),
        ("git@example.com:example/y.git/", "y"),
        ("/srv/x/.git", "x"),
        ("/srv/z/", "z"),
        ("/srv/z//", "z"),
        ("/srv/w", "w"),
        ("host:repo.git", "repo"),
        ("host:repo", "repo"),
        ("/srv/a.git.git", "a.git"),
        ("/srv/.git", "srv"),
        ("host:.git", ""),
        ("host:", ""),
    ],
)
def test_url_basename_follows_the_order_of_the_design(url, expected):
    assert registry.basename(url) == expected


def test_an_empty_basename_leaves_the_entry_without_an_id(tmp_path):
    res = resolved(tmp_path, "repos:\n  - url: 'host:'\n", source(url="{url}"))
    assert res.entries[0].id is None
    assert rendered(res) == [
        "registry.yaml: repos[0]: the id cannot be determined: the URL gives no basename; "
        "set `id` to the key that holds the id, or fix the URL"
    ]


def test_an_entry_whose_url_is_unknown_is_not_also_reported_as_without_an_id(tmp_path):
    res = resolved(tmp_path, "repos:\n  - repo: 5\n")
    assert [p.msg_id for p in res.problems] == ["entry-value"]


# check 2: values


def test_a_missing_key_reads_as_absent_in_japanese(tmp_path):
    res = resolved(tmp_path, "repos:\n  - {}\n", lang="ja")
    assert "空でない文字列でなければならないが，キーがない．" in only(res, "`repo`")


@pytest.mark.parametrize(
    "item, kind",
    [
        ("{}", "absent"),
        ("{repo: }", "null"),
        ("{repo: ''}", "an empty string"),
        ("{repo: 5}", "a number"),
        ("{repo: on}", "a boolean"),
        ("{repo: 2026-01-01}", "a date"),
        ("{repo: [a]}", "a list"),
    ],
)
def test_a_placeholder_that_is_not_a_non_empty_string_is_reported_by_position(tmp_path, item, kind):
    res = resolved(tmp_path, f"repos:\n  - {item}\n")
    assert res.entries[0].url is None
    line = only(res, "`repo` must be")
    assert line.startswith("registry.yaml: repos[0]: `repo` must be a non-empty string")
    assert f"but it is {kind};" in line


def test_a_key_that_is_both_a_placeholder_and_the_id_key_is_reported_once(tmp_path):
    res = resolved(tmp_path, "repos:\n  - other: 1\n", source(url="{name}", id="name"))
    assert [p.msg_id for p in res.problems] == ["entry-value"]


def test_every_missing_placeholder_is_reported(tmp_path):
    spec = source(url="git@example.com:{owner}/{repo}.git", id="name")
    res = resolved(tmp_path, "repos:\n  - name: a\n", spec)
    assert len(rendered(res)) == 2
    assert res.entries[0].id == "a"


def test_a_value_is_substituted_once_even_if_it_holds_braces(tmp_path):
    spec = source(url="git@example.com:{repo}.git", id="name")
    res = resolved(tmp_path, "repos:\n  - name: a\n    repo: 'example/{name}'\n", spec)
    assert res.entries[0].url == "git@example.com:example/{name}.git"


@pytest.mark.parametrize("scalar", ["on", "2026-01-01", "5", "''", "null"])
def test_an_id_that_yaml_does_not_read_as_a_string_is_a_problem(tmp_path, scalar):
    spec = source(url="{url}", id="name")
    text = f"repos:\n  - name: {scalar}\n    url: /srv/x.git\n"
    res = resolved(tmp_path, text, spec)
    assert res.entries[0].id is None
    line = only(res, "`name` must be")
    assert line.startswith("registry.yaml: repos[0]: ")


@pytest.mark.parametrize("aliases", ["on", "[on]", "[5]", "['']", "{a: b}", "x"])
def test_aliases_must_be_a_list_of_non_empty_strings(tmp_path, aliases):
    spec = source(id="name", aliases="aliases")
    text = f"repos:\n  - name: a\n    repo: example/a\n    aliases: {aliases}\n"
    res = resolved(tmp_path, text, spec)
    assert "`aliases` must be a list of non-empty strings" in only(res, "`aliases`")


def test_absent_and_null_aliases_mean_none(tmp_path):
    spec = source(id="name", aliases="aliases")
    text = "repos:\n  - {name: a, repo: example/a}\n  - {name: b, repo: example/b, aliases: }\n"
    res = resolved(tmp_path, text, spec)
    assert rendered(res) == []
    assert [e.aliases for e in res.entries] == [(), ()]


@pytest.mark.parametrize(
    "value",
    ['"a\\tb"', '"a\\nb"', '"a b"', '"a\\u00a0b"', '"a\\x01b"', '"a\\x81b"', '"a\\u2028b"'],
)
def test_whitespace_or_a_control_character_in_an_id_is_a_problem_and_stays_on_one_line(tmp_path, value):
    spec = source(id="name")
    res = resolved(tmp_path, f"repos:\n  - name: {value}\n    repo: example/a\n", spec)
    (problem,) = [p for p in res.problems if "whitespace or a control character" in p.text]
    assert "\n" not in problem.render() and "\t" not in problem.render()
    assert problem.render().startswith("registry.yaml: repos[0] (a")


def test_whitespace_in_an_alias_is_a_problem(tmp_path):
    spec = source(id="name", aliases="aliases")
    text = 'repos:\n  - name: a\n    repo: example/a\n    aliases: ["b c"]\n'
    res = resolved(tmp_path, text, spec)
    assert "alias `b c` contains whitespace" in only(res, "alias")


def test_a_tab_or_newline_in_a_url_is_a_problem(tmp_path):
    res = resolved(tmp_path, 'repos:\n  - repo: "example/a\\nb"\n')
    assert "URL `git@example.com:example/a\\nb.git` contains whitespace" in only(res, "URL `")


@pytest.mark.parametrize("which", ["id", "alias"])
def test_an_id_or_alias_beginning_with_a_dash_is_a_problem(tmp_path, which):
    spec = source(id="name", aliases="aliases")
    if which == "id":
        text = "repos:\n  - {name: -a, repo: example/a}\n"
    else:
        text = "repos:\n  - {name: a, repo: example/a, aliases: [-b]}\n"
    res = resolved(tmp_path, text, spec)
    assert f"{which} `-" in only(res, "begins with `-`")


# check 3: directory names


@pytest.mark.parametrize("name", [".", "..", "a/b", "a\\\\b", "-x"])
def test_a_directory_name_that_is_not_one_path_component_is_a_problem(tmp_path, name):
    spec = source(id="name")
    res = resolved(tmp_path, f'repos:\n  - name: "{name}"\n    repo: example/a\n', spec)
    assert "is not one path component" in only(res, "path component")
    assert res.entries[0].dir is None
    assert res.entries[0].destination is None


def test_an_empty_url_basename_is_a_directory_problem_when_dir_is_url(tmp_path):
    spec = source(url="{url}", id="name", dir="url")
    res = resolved(tmp_path, "repos:\n  - {name: a, url: 'host:'}\n", spec)
    assert "directory name `` is not one path component" in only(res, "path component")


# check 4: ids


def test_a_collision_between_two_sources_names_both_entries(tmp_path):
    text = "one:\n  - repo: example/a\ntwo:\n  - repo: example-org/a\n"
    res = resolved(tmp_path, text, source(entries="one[]"), source(entries="two[]"))
    line = only(res, "also an id or alias")
    assert line == "registry.yaml: two[0] (a): `a` is also an id or alias of registry.yaml: one[0]; rename one of them"
    first, second = res.entries
    assert res.problems_for(first) and res.problems_for(second)


def test_an_alias_colliding_with_another_entrys_id_is_a_problem(tmp_path):
    spec = source(id="name", aliases="aliases")
    text = "repos:\n  - {name: a, repo: example/a}\n  - {name: b, repo: example/b, aliases: [a]}\n"
    res = resolved(tmp_path, text, spec)
    assert "registry.yaml: repos[1] (b): `a` is also" in only(res, "also an id")


def test_an_excluded_entry_still_counts_for_uniqueness(tmp_path):
    text = "repos:\n  - repo: example/a\n  - repo: example-org/a\n"
    res = resolved(tmp_path, text, source(exclude=["a"]))
    only(res, "also an id or alias")
    assert all(e.excluded for e in res.entries)


def test_an_alias_equal_to_its_own_id_is_a_problem_once(tmp_path):
    spec = source(id="name", aliases="aliases")
    text = "repos:\n  - {name: a, repo: example/a, aliases: [a, a]}\n"
    res = resolved(tmp_path, text, spec)
    assert only(res, "equals the entry's own id").endswith("remove it from the aliases")
    assert len(rendered(res)) == 1


def test_an_alias_repeated_within_its_entry_is_a_problem(tmp_path):
    spec = source(id="name", aliases="aliases")
    text = "repos:\n  - {name: a, repo: example/a, aliases: [b, b]}\n"
    res = resolved(tmp_path, text, spec)
    assert "alias `b` is listed more than once" in only(res, "more than once")


def test_ids_are_compared_exactly(tmp_path):
    res = resolved(tmp_path, slugs("example/a", "example/A"))
    assert [p.msg_id for p in res.problems] == ["dest-overlap"]  # case folding is for destinations


# check 5: URLs


def test_a_url_that_no_pattern_matches_is_a_problem(tmp_path):
    res = resolved(tmp_path, slugs("someone-else/a", "example/b"))
    line = only(res, "matches no pattern")
    assert line.startswith("registry.yaml: repos[0] (a): URL `git@example.com:someone-else/a.git`")


@pytest.mark.parametrize("url", ["host::evil", "ext::sh", "a+b.c-d::x"])
def test_a_remote_helper_url_is_a_problem_whatever_the_patterns_say(tmp_path, url):
    # `host:*` admits `host::evil`, but git would run `git-remote-host` for it
    res = resolved(tmp_path, f"repos:\n  - url: {url}\n", source(url="{url}"))
    assert [p.msg_id for p in res.problems] == ["url-helper"]
    assert "remote-helper syntax" in only(res, "URL `")
    assert res.problems_for(res.entries[0])


def test_a_double_colon_that_does_not_follow_a_transport_is_not_a_helper(tmp_path):
    res = resolved(tmp_path, "repos:\n  - url: 'host:a::b'\n", source(url="{url}"))
    assert rendered(res) == []


def test_a_pattern_star_does_not_cross_a_slash(tmp_path):
    res = resolved(tmp_path, slugs("example/deeper/a"))
    only(res, "matches no pattern")


# checks 6 and 7: declared deviations


def deviation(tmp_path, value: str):
    text = f"repos:\n  - repo: example/a\n    local: {json.dumps(value)}\n"
    return resolved(tmp_path, text, source(local="local"))


@pytest.mark.parametrize(
    "value",
    [
        "relative/path",
        "~",
        "~/",
        "$HOME",
        "${HOME}/src/a",
        "$1X/src/a",
        "~/src//a",
        "~/src/./a",
        "~/src/../a",
        "~/src/a/",
        "~/src/a\tb",
        "~/src/a\nb",
        "~/src/a\u0085b",
        "~/src/a\x81b",
        "~/src/a\u2028b",
        "~/src/a\u2029b",
        "",
    ],
)
def test_a_deviation_in_a_form_the_design_does_not_allow_is_a_problem(tmp_path, value):
    res = deviation(tmp_path, value)
    assert "must be `~/<path>`, `/<path>` or `$NAME/<path>`" in only(res, "declared deviation")
    assert "\n" not in only(res, "declared deviation")


@pytest.mark.parametrize("value", ["~/elsewhere/a", "/srv/a", "~/srv/a", "~/src"])
def test_a_deviation_outside_every_root_is_a_problem_that_says_to_exclude(tmp_path, value):
    res = deviation(tmp_path, value)
    assert "lies outside every root" in only(res, "declared deviation")
    assert "or exclude the entry instead" in rendered(res)[0]


def test_a_deviation_that_is_not_a_string_is_a_problem(tmp_path):
    text = "repos:\n  - repo: example/a\n    local: [x]\n"
    res = resolved(tmp_path, text, source(local="local"))
    assert "`local` must be a string, but it is a list" in only(res, "`local`")


def test_a_deviation_equal_to_the_default_destination_is_a_problem_that_says_delete(tmp_path):
    res = deviation(tmp_path, "~/src/a")
    assert "equals the default destination; delete the `local` value" in only(res, "default")


def test_a_deviation_equal_to_the_default_of_another_root_is_not_check_seven(tmp_path):
    res = deviation(tmp_path, "~/src/ops/a")
    assert rendered(res) == []


def test_a_deviation_is_spelt_in_a_variable_root_the_same_way(tmp_path):
    text = "repos:\n  - repo: example/a\n    local: $DATA/other\n"
    res = resolved(tmp_path, text, source(local="local"), roots='{ work = "~/src", data = "$DATA" }')
    assert rendered(res) == []
    assert res.entries[0].root == "data"


# check 8: destinations


def test_destinations_differing_only_in_case_conflict(tmp_path):
    res = resolved(tmp_path, slugs("example/Foo", "example/foo"))
    line = only(res, "destination")
    assert line.startswith("registry.yaml: repos[1] (foo): destination `~/src/foo` equals, contains")
    assert "`~/src/Foo` of registry.yaml: repos[0]" in line
    assert all(res.problems_for(e) for e in res.entries)


def test_destinations_differing_only_in_unicode_normalisation_conflict(tmp_path):
    res = resolved(tmp_path, slugs("example/caf\u00e9", "example/cafe\u0301"))
    only(res, "destination")
    assert "id-collision" not in [p.msg_id for p in res.problems]  # ids compare exactly


def test_a_destination_inside_another_destination_conflicts(tmp_path):
    text = "repos:\n  - repo: example/a\n  - repo: example/b\n    local: ~/src/a/b\n"
    res = resolved(tmp_path, text, source(local="local"))
    assert "of registry.yaml: repos[0]" in only(res, "destination")


def test_a_destination_equal_to_a_root_conflicts(tmp_path):
    res = resolved(tmp_path, slugs("example/ops"))
    line = only(res, "root `ops`")
    assert "destination `~/src/ops` equals or contains root `ops` (`~/src/ops`)" in line


def test_a_destination_containing_a_root_conflicts(tmp_path):
    text = "repos:\n  - repo: example/a\n    local: ~/src/ops\n"
    res = resolved(tmp_path, text, source(local="local"), roots='{ work = "~/src", ops = "~/src/ops/x" }')
    assert "root `ops`" in only(res, "root")


def test_a_destination_inside_a_root_is_fine(tmp_path):
    assert rendered(resolved(tmp_path, slugs("example/a"))) == []


def test_sibling_destinations_with_a_common_prefix_do_not_conflict(tmp_path):
    assert rendered(resolved(tmp_path, slugs("example/a", "example/ab", "example/a-b"))) == []


def test_excluded_entries_take_no_part_in_destination_checks(tmp_path):
    res = resolved(tmp_path, slugs("example/ops", "example/x"), source(exclude=["ops"]))
    assert rendered(res) == []


# excluded entries, check 9


def test_an_excluded_entry_takes_part_in_no_check_but_four_and_nine(tmp_path):
    text = (
        "repos:\n"
        "  - repo: someone-else/a\n    local: /nowhere\n"
        "  - repo: 5\n"
    )
    res = resolved(tmp_path, text, source(local="local", exclude=["a"]))
    # only the second entry, whose URL cannot be built
    assert [p.msg_id for p in res.problems] == ["entry-value"]
    assert res.entries[0].excluded and res.entries[0].destination is None


def test_an_exclude_that_matches_an_alias_excludes_the_entry(tmp_path):
    spec = source(id="name", aliases="aliases", exclude=["nick"])
    res = resolved(tmp_path, "repos:\n  - {name: a, repo: someone/a, aliases: [nick]}\n", spec)
    assert rendered(res) == []
    assert res.entries[0].excluded


def test_an_exclude_that_matches_no_entry_is_reported_against_the_configuration(tmp_path):
    res = resolved(tmp_path, slugs("example/a"), source(exclude=["ghost", "ghost"]))
    assert rendered(res) == [
        "mgtk-repo-utils.toml: clone.sources[0]: `exclude` lists `ghost`, which matches no id or "
        "alias of the source's entries; remove it, or fix the id"
    ]


def test_an_exclude_is_matched_within_its_own_source_only(tmp_path):
    text = "one:\n  - repo: example/a\ntwo:\n  - repo: example/b\n"
    res = resolved(
        tmp_path, text, source(entries="one[]", exclude=["b"]), source(entries="two[]")
    )
    assert "clone.sources[0]" in only(res, "`exclude` lists `b`")


# what attaches to an entry (design section 16, step 1)


def test_only_the_problems_of_the_entry_attach_to_it(tmp_path):
    text = (
        "repos:\n"
        "  - repo: example/a\n"
        "  - repo: someone-else/b\n"
        "  - 5\n"
    )
    res = resolved(tmp_path, text, source(exclude=["ghost"]))
    good, bad = res.entries
    assert res.problems_for(good) == []  # a walk error, an unmatched exclude and another entry's URL
    assert [p.msg_id for p in res.problems_for(bad)] == ["url-unmatched"]
    assert len(res.problems) == 3


def test_a_conflict_attaches_to_both_sides_and_not_to_a_third(tmp_path):
    res = resolved(tmp_path, slugs("example/a", "example/A", "example/c"))
    first, second, third = res.entries
    assert len(res.problems_for(first)) == len(res.problems_for(second)) == 1
    assert res.problems_for(third) == []


def test_an_id_colliding_with_an_alias_attaches_to_both(tmp_path):
    spec = source(id="name", aliases="aliases")
    text = "repos:\n  - {name: a, repo: example/a}\n  - {name: b, repo: example/b, aliases: [a]}\n"
    res = resolved(tmp_path, text, spec)
    assert [len(res.problems_for(e)) for e in res.entries] == [1, 1]


def test_find_returns_excluded_entries_and_the_first_of_a_collision(tmp_path):
    res = resolved(tmp_path, slugs("example/a", "example-org/a", "example/b"), source(exclude=["b"]))
    assert res.find("b").excluded
    assert res.find("a") is res.entries[0]


# expansion


ENV = {"HOME": "/home/user", "WORK": "/data/work/", "REL": "relative", "TAB": "/a\tb", "EMPTY": ""}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("~/src", "/home/user/src"),
        ("~/src/a b", "/home/user/src/a b"),
        ("$WORK", "/data/work/"),
        ("$WORK/x", "/data/work/x"),
        ("/abs/path", "/abs/path"),
    ],
)
def test_expand_reads_home_and_the_named_variable(text, expected):
    assert registry.expand(text, "work", ENV, "en") == expected


def test_expand_ignores_the_real_environment_when_one_is_given(monkeypatch):
    monkeypatch.setenv("HOME", "/somewhere/else")
    assert registry.expand("~/a", "work", {"HOME": "/h"}, "en") == "/h/a"


def test_expand_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("HOME", "/from/process")
    assert registry.expand("~/a", "work", None, "en") == "/from/process/a"


@pytest.mark.parametrize(
    "text, variable",
    [("~/src", "HOME"), ("$NOPE", "NOPE"), ("$EMPTY/x", "EMPTY")],
)
def test_expand_names_an_unset_variable_and_the_root(text, variable):
    with pytest.raises(ToolError) as caught:
        registry.expand(text, "work", {"EMPTY": ""}, "en")
    assert f"`{variable}` is unset or empty" in str(caught.value)
    assert "root `work`" in str(caught.value)


@pytest.mark.parametrize("variable", ["REL", "TAB"])
def test_expand_refuses_a_relative_value_or_one_with_a_control_character(variable):
    with pytest.raises(ToolError, match=f"`{variable}` is `"):
        registry.expand(f"${variable}", "work", ENV, "en")


def make_entry(tmp_path, text, **keys):
    res = resolved(tmp_path, text, source(**keys), roots='{ work = "$WORK", home = "~/src" }')
    assert rendered(res) == []
    return res, res.entries[0]


def test_destination_is_the_root_without_its_trailing_slash_then_the_directory(tmp_path):
    res, entry = make_entry(tmp_path, slugs("example/a"))
    assert registry.expand_destination(entry, {"work": "$WORK"}, ENV) == "/data/work/a"


def test_destination_of_a_deviation_is_the_expanded_deviation(tmp_path):
    text = "repos:\n  - repo: example/a\n    local: ~/src/odd name\n"
    res, entry = make_entry(tmp_path, text, local="local")
    assert registry.expand_destination(entry, {"work": "$WORK", "home": "~/src"}, ENV) == (
        "/home/user/src/odd name"
    )


def test_only_the_entrys_own_root_is_expanded(tmp_path):
    res, entry = make_entry(tmp_path, slugs("example/a"))
    env = {"WORK": "/w"}  # HOME, the other root's variable, is unset
    assert registry.expand_destination(entry, {"work": "$WORK", "home": "~/src"}, env) == "/w/a"


def test_a_root_of_a_single_slash_gives_a_destination_directly_under_it(tmp_path):
    res, entry = make_entry(tmp_path, slugs("example/a"))
    assert registry.expand_destination(entry, {"work": "$WORK"}, {"WORK": "/"}) == "/a"


# routed roots, sets and --route (design sections 13 and 14, revision 6)

TWO_ROOTS = '{ work = "~/src", templates = "~/tpl" }'
BY_CLASS = {"by": "class", "map": {"project": "work", "template": "templates"}}


def routed(**keys: object) -> str:
    return source(root=BY_CLASS, **keys)


def routed_resolved(tmp_path, text, **keys):
    return resolved(tmp_path, text, routed(**keys), roots=TWO_ROOTS)


def test_a_routed_root_takes_the_root_the_entrys_value_selects(tmp_path):
    res = routed_resolved(tmp_path, "repos:\n  - {repo: example/a, class: template}\n")
    assert rendered(res) == []
    assert (res.entries[0].root, res.entries[0].destination) == ("templates", "~/tpl/a")


@pytest.mark.parametrize("value", ["", "    class:\n"])
def test_an_absent_or_null_routing_value_takes_the_default(tmp_path, value):
    text = "repos:\n  - repo: example/a\n" + (value and "    class:\n")
    res = routed_resolved(tmp_path, text, defaults={"class": "template"})
    assert rendered(res) == []
    assert (res.entries[0].root, res.entries[0].destination) == ("templates", "~/tpl/a")


def test_a_present_value_beats_the_default(tmp_path):
    text = "repos:\n  - {repo: example/a, class: project}\n"
    res = routed_resolved(tmp_path, text, defaults={"class": "template"})
    assert res.entries[0].root == "work"


def test_an_absent_routing_value_without_a_default_is_check_10_and_leaves_no_destination(tmp_path):
    res = routed_resolved(tmp_path, "repos:\n  - repo: example/a\n")
    line = only(res, "`class`")
    assert "registry.yaml: repos[0] (a)" in line and "absent" in line
    entry = res.entries[0]
    assert entry.destination is None
    assert [p.render() for p in res.problems_for(entry)] == [line]


def test_a_null_routing_value_without_a_default_is_check_10(tmp_path):
    res = routed_resolved(tmp_path, "repos:\n  - {repo: example/a, class: null}\n")
    assert "null" in only(res, "`class`")


def test_a_routing_value_missing_from_the_map_is_check_10(tmp_path):
    res = routed_resolved(tmp_path, "repos:\n  - {repo: example/a, class: other}\n")
    assert "`class` is `other`, which `root.map` does not list" in only(res, "root.map")
    assert res.entries[0].destination is None


@pytest.mark.parametrize(
    ("scalar", "kind"), [("3", "a number"), ("on", "a boolean"), ("[project]", "a list")]
)
def test_a_routing_value_that_is_not_a_string_is_check_10(tmp_path, scalar, kind):
    res = routed_resolved(tmp_path, f"repos:\n  - {{repo: example/a, class: {scalar}}}\n")
    assert f"`class` selects the root of the entry through `root.map`, but it is {kind}" in only(
        res, "`class`"
    )


def test_a_default_never_fills_the_id_or_a_placeholder(tmp_path):
    res = routed_resolved(
        tmp_path,
        "repos:\n  - {class: project}\n",
        defaults={"repo": "example/zzz"},
    )
    assert "`repo` must be a non-empty string" in only(res, "`repo`")


def test_an_excluded_entry_with_an_unroutable_value_has_no_problem(tmp_path):
    res = routed_resolved(tmp_path, "repos:\n  - {repo: example/a, class: other}\n", exclude=["a"])
    assert rendered(res) == []


def test_a_source_is_named_by_its_declared_name_in_problems(tmp_path):
    res = resolved(tmp_path, "repos: []\n", source(name="services"))
    assert "mgtk-repo-utils.toml: services:" in only(res, "no entry")


SET_REGISTRY = (
    "repos:\n"
    "  - {repo: example/a, status: active, class: project}\n"
    "  - {repo: example/b, status: archived, class: project}\n"
    "  - {repo: example/c, status: active, class: template}\n"
    "  - {repo: example/d, status: active}\n"
    "  - {repo: example/e, status: true, class: project}\n"
)


def members(res, name):
    return [entry.id for entry in res.set_entries(name)]


def test_an_empty_condition_admits_every_entry_of_the_source(tmp_path):
    res = routed_resolved(tmp_path, SET_REGISTRY, defaults={"class": "project"}, sets={"all": {}})
    assert members(res, "all") == ["a", "b", "c", "d", "e"]


def test_a_condition_with_several_keys_needs_every_key_to_match_one_of_its_values(tmp_path):
    sets = {"live": {"status": ["active", "archived"], "class": ["project"]}}
    res = routed_resolved(tmp_path, SET_REGISTRY, sets=sets)
    assert members(res, "live") == ["a", "b"]  # c is a template, d has no class, e's status is a boolean


def test_a_default_counts_for_a_set_condition(tmp_path):
    sets = {"projects": {"class": ["project"]}}
    res = routed_resolved(tmp_path, SET_REGISTRY, sets=sets, defaults={"class": "project"})
    assert members(res, "projects") == ["a", "b", "d", "e"]


def test_a_value_that_is_not_a_string_matches_no_condition(tmp_path):
    res = routed_resolved(
        tmp_path, SET_REGISTRY, defaults={"class": "project"}, sets={"s": {"status": ["true", "on"]}}
    )
    assert members(res, "s") == []


def test_excluded_entries_belong_to_no_set(tmp_path):
    res = routed_resolved(
        tmp_path, SET_REGISTRY, defaults={"class": "project"}, sets={"all": {}}, exclude=["b"]
    )
    assert members(res, "all") == ["a", "c", "d", "e"]


def test_a_set_declared_by_two_sources_is_their_union_in_source_then_entry_order(tmp_path):
    (tmp_path / "other.yaml").write_text("repos:\n  - repo: example/z\n  - repo: example/y\n")
    res = resolved(
        tmp_path,
        "repos:\n  - repo: example/a\n  - repo: example/b\n",
        source(sets={"all": {}}),
        source(file="other.yaml", sets={"all": {}, "extra": {}}),
        source(file="other.yaml", url="git@example.com:example-org/{repo}.git", name="third"),
    )
    assert members(res, "all") == ["a", "b", "z", "y"]
    assert res.set_names == ("all", "extra")
    assert members(res, "extra") == ["z", "y"]


def test_a_set_no_source_declares_is_not_declared(tmp_path):
    res = resolved(tmp_path, slugs("example/a"), source(sets={"all": {}}))
    assert res.declares_set("all") and not res.declares_set("active")
    assert members(res, "active") == []


def test_a_source_without_sets_belongs_to_no_set(tmp_path):
    res = resolved(tmp_path, slugs("example/a"))
    assert res.set_names == () and res.entries[0].sets == frozenset()


def test_an_entry_with_a_problem_stays_in_its_set_with_its_problems(tmp_path):
    res = routed_resolved(
        tmp_path,
        "repos:\n  - {repo: example/a, class: project}\n  - {repo: example/b, class: other}\n",
        sets={"all": {}},
    )
    bad = res.set_entries("all")[1]
    assert bad.id == "b" and len(res.problems_for(bad)) == 1


# route


def routing(tmp_path, text=None, sources=None, roots=TWO_ROOTS):
    sources = sources or [routed(name="projects", defaults={"class": "project"})]
    config = configure(tmp_path, text if text is not None else slugs("example/a"), *sources, roots=roots)
    return config, registry.load(config)


def test_route_builds_the_entry_the_source_would_build(tmp_path):
    config, res = routing(tmp_path)
    entry, problems = registry.route(config, res, "projects", ["repo=example/b", "class=template"])
    assert problems == []
    assert (entry.id, entry.url, entry.root, entry.destination, entry.dir) == (
        "b",
        "git@example.com:example/b.git",
        "templates",
        "~/tpl/b",
        "b",
    )
    assert len(res.entries) == 1  # the registry is not changed


def test_route_chooses_the_root_by_the_given_field_and_otherwise_by_defaults(tmp_path):
    config, res = routing(tmp_path)
    given, _ = registry.route(config, res, "projects", ["repo=example/b", "class=template"])
    default, _ = registry.route(config, res, "projects", ["repo=example/b"])
    assert (given.root, default.root) == ("templates", "work")


def test_route_reports_an_id_the_registry_already_declares(tmp_path):
    config, res = routing(tmp_path)
    _, problems = registry.route(config, res, "projects", ["repo=example-org/a"])
    assert any("also an id or alias of registry.yaml: repos[0]" in p.render() for p in problems)


def test_route_reports_a_destination_nested_in_an_existing_one(tmp_path):
    text = "repos:\n  - {repo: example/a, local: ~/src/deep}\n"
    config, res = routing(tmp_path, text, [routed(name="projects", defaults={"class": "project"}, local="local")])
    _, problems = registry.route(config, res, "projects", ["repo=example/b", "local=~/src/deep/inner"])
    assert len(problems) == 1
    assert "~/src/deep/inner" in problems[0].render() and "registry.yaml: repos[0]" in problems[0].render()


def test_route_checks_a_given_local_as_a_declared_deviation(tmp_path):
    config, res = routing(tmp_path, sources=[routed(name="projects", defaults={"class": "project"}, local="local")])
    outside = registry.route(config, res, "projects", ["repo=example/b", "local=/elsewhere/b"])[1]
    same = registry.route(config, res, "projects", ["repo=example/b", "local=~/src/b"])[1]
    ok, none = registry.route(config, res, "projects", ["repo=example/b", "local=~/src/odd"])
    assert len(outside) == 1 and "outside every root" in outside[0].render()
    assert len(same) == 1 and "equals the default destination" in same[0].render()
    assert none == [] and (ok.deviation, ok.destination) == ("~/src/odd", "~/src/odd")


def test_route_reports_an_unroutable_value(tmp_path):
    config, res = routing(tmp_path)
    _, problems = registry.route(config, res, "projects", ["repo=example/b", "class=other"])
    assert len(problems) == 1 and "root.map" in problems[0].render()


def test_route_does_not_report_the_registrys_own_problems(tmp_path):
    text = "repos:\n  - {repo: example/a, class: other}\n"
    config, res = routing(tmp_path, text)
    assert res.problems
    _, problems = registry.route(config, res, "projects", ["repo=example/b"])
    assert problems == []


def test_route_into_a_source_without_a_name_names_the_known_names(tmp_path):
    config, res = routing(tmp_path, sources=[routed(), routed(name="projects")])
    with pytest.raises(ToolError) as info:
        registry.route(config, res, "clone.sources[0]", ["repo=example/b"])
    assert "no source is named `clone.sources[0]`" in str(info.value) and "`projects`" in str(info.value)


def test_route_with_no_named_source_says_none(tmp_path):
    config, res = routing(tmp_path, sources=[routed()])
    with pytest.raises(ToolError) as info:
        registry.route(config, res, "projects", [])
    assert "the named sources are none" in str(info.value)


@pytest.mark.parametrize("field", ["repo", "=x", ""])
def test_route_rejects_a_field_that_is_not_key_equals_value(tmp_path, field):
    config, res = routing(tmp_path)
    with pytest.raises(ToolError) as info:
        registry.route(config, res, "projects", [field])
    assert "<key>=<value>" in str(info.value)


def test_route_splits_a_field_at_the_first_equals_sign(tmp_path):
    config, res = routing(tmp_path, sources=[routed(name="projects", defaults={"class": "project"}, url="{repo}")])
    entry, _ = registry.route(config, res, "projects", ["repo=/srv/a=b"])
    assert entry.url == "/srv/a=b"


def test_route_refuses_an_excluded_id(tmp_path):
    config, res = routing(tmp_path, sources=[routed(name="projects", defaults={"class": "project"}, exclude=["b"])])
    with pytest.raises(ToolError) as info:
        registry.route(config, res, "projects", ["repo=example/b"])
    assert "excluded" in str(info.value)
