# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from mgtk_repo_utils import __version__
from mgtk_repo_utils.config import ConfigError, load, resolve_config_path, resolve_root
from support import Repo


def load_text(tmp_path: Path, text: str):
    path = tmp_path / "mgtk-repo-utils.toml"
    path.write_text(text, encoding="utf-8")
    return load(path, tmp_path)


def fail(tmp_path: Path, text: str) -> str:
    with pytest.raises(ConfigError) as info:
        load_text(tmp_path, text)
    return str(info.value)


def test_minimal_file_has_no_tools_enabled(tmp_path):
    config = load_text(tmp_path, "schema = 1\n")
    assert config.lang == "en"
    assert (config.table("issues"), config.table("freeze"), config.table("links")) == (None, None, None)


def test_issues_defaults_are_exactly_the_documented_ones(tmp_path):
    cfg = load_text(tmp_path, "schema = 1\n[issues]\n").table("issues")
    assert cfg is not None
    assert (cfg.dir, cfg.items, cfg.template) == ("issues", "items", "_template.md")
    assert (cfg.read, cfg.untracked, cfg.untracked_rows) == ("tracked", "warn", "warn")
    assert cfg.id_pattern == r"\d{8}_[a-z0-9-]+"
    assert cfg.id_regex.fullmatch("20260101_a-b")
    assert (cfg.id_field, cfg.title, cfg.items_allow) == ("required", "field", ())
    assert cfg.active == ("in_progress", "blocked", "open")
    assert cfg.deferred == ("deferred",)
    assert cfg.terminal == ("closed", "wont_fix")
    assert cfg.status_check is True
    assert (cfg.priority, cfg.type, cfg.on_terminal) == ((), (), ())
    assert cfg.closed_only_when_terminal is False
    assert cfg.views == ()


def test_view_defaults_are_exactly_the_documented_ones(tmp_path):
    text = 'schema = 1\nlang = "ja"\n[issues.views."README.md"]\nmarker = "m"\n'
    (view,) = load_text(tmp_path, text).table("issues").views
    assert view.file == "README.md"
    assert view.lang == "ja"
    assert view.show == ("counts", "active", "deferred")
    assert view.sections is True
    assert view.link == "issue"
    assert view.columns == ("issue", "title", "created")
    assert view.extra_columns == {}
    assert view.sort == ("created",)
    assert view.group_by == ""
    assert view.empty == "nothing"


def test_id_pattern_is_ascii_only(tmp_path):
    cfg = load_text(tmp_path, "schema = 1\n[issues]\n").table("issues")
    assert not cfg.id_regex.fullmatch("２０２６０１０１_a")


def test_freeze_and_links_defaults(tmp_path):
    config = load_text(tmp_path, 'schema = 1\n[freeze]\npaths = [".x"]\n[links]\n')
    assert (config.table("freeze").allow, config.table("freeze").mode, config.table("freeze").reason) == ((), "subset", "")
    assert config.table("freeze").paths == (".x",)
    assert (config.table("links").read, config.table("links").untracked) == ("tracked", "warn")
    assert (config.table("links").anchors, config.table("links").exclude, config.table("links").ignore_targets) == (
        False,
        (),
        (),
    )


def test_full_example_of_the_design_is_accepted(tmp_path):
    text = """
schema = 1
requires = "0.1"
lang = "ja"
[issues]
dir = "issues"
items = "items"
template = "_template.md"
read = "tracked"
untracked = "warn"
untracked_rows = "warn"
id_pattern = '\\d{8}_[a-z0-9-]+'
id_field = "required"
title = "field"
items_allow = [".gitkeep"]
[issues.status]
active = ["in_progress", "blocked", "open"]
deferred = ["deferred"]
terminal = ["closed", "wont_fix"]
check = true
[issues.fields]
priority = ["critical", "high", "medium", "low"]
type = ["bug", "feature", "task", "chore", "question"]
on_terminal = ["closed", "closed_by"]
closed_only_when_terminal = true
[issues.views."README.md"]
marker = "issues-active"
lang = "ja"
show = ["counts", "active", "deferred"]
sections = true
link = "issue"
columns = ["issue", "title", "priority", "created"]
extra_columns = { blocked = ["blocked_by"] }
sort = ["priority", "created"]
group_by = ""
empty = "nothing"
[freeze]
paths = [".vscode"]
allow = []
mode = "subset"
reason = ""
[links]
read = "tracked"
untracked = "warn"
anchors = true
exclude = ["archive/**"]
ignore_targets = ['^\\$']
"""
    config = load_text(tmp_path, text)
    assert config.table("issues").views[0].extra_columns == {"blocked": ("blocked_by",)}
    assert config.table("links").anchors is True


def test_missing_file_is_an_error_naming_the_remedy(tmp_path):
    with pytest.raises(ConfigError, match="--config"):
        load(tmp_path / "absent.toml", tmp_path)


def test_invalid_toml_is_an_error(tmp_path):
    assert "invalid TOML" in fail(tmp_path, "schema = \n")


def test_schema_is_required(tmp_path):
    assert "schema = 1" in fail(tmp_path, "lang = 'en'\n")


@pytest.mark.parametrize("value", ["2", '"1"'])
def test_schema_must_be_one(tmp_path, value):
    fail(tmp_path, f"schema = {value}\n")


def test_requires_newer_than_this_copy_names_both_versions(tmp_path):
    message = fail(tmp_path, 'schema = 1\nrequires = "9.0"\n')
    assert "9.0" in message and __version__ in message


def test_requires_satisfied_by_this_release(tmp_path):
    load_text(tmp_path, 'schema = 1\nrequires = "0.1"\n')
    load_text(tmp_path, 'schema = 1\nrequires = "0.1.0"\n')


def test_requires_must_look_like_a_version(tmp_path):
    fail(tmp_path, 'schema = 1\nrequires = "latest"\n')
    fail(tmp_path, "schema = 1\nrequires = 1\n")


def test_requires_is_checked_before_unknown_keys_so_newer_files_explain_themselves(tmp_path):
    message = fail(tmp_path, 'schema = 1\nrequires = "9.0"\nfuture_key = 1\n')
    assert "requires" in message


@pytest.mark.parametrize(
    "text",
    [
        "schema = 1\nlangg = 'en'\n",
        "schema = 1\n[issues]\nreed = 'tracked'\n",
        "schema = 1\n[issues.status]\nactive = []\nchek = true\n",
        "schema = 1\n[issues.fields]\nprio = []\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\ncolumn = []\n",
        "schema = 1\n[freeze]\npaths = []\nmodus = 'x'\n",
        "schema = 1\n[links]\nanchor = true\n",
    ],
)
def test_unknown_keys_are_errors_naming_this_version(tmp_path, text):
    message = fail(tmp_path, text)
    assert "unknown" in message and __version__ in message


def test_unknown_table_is_an_error(tmp_path):
    message = fail(tmp_path, "schema = 1\n[issues.bogus]\nx = 1\n")
    assert "unknown table" in message and "issues.bogus" in message
    assert "unknown table" in fail(tmp_path, "schema = 1\n[future]\n")


@pytest.mark.parametrize(
    "text",
    [
        "schema = 1\nlang = 3\n",
        "schema = 1\n[issues]\ndir = 3\n",
        "schema = 1\n[issues]\nitems_allow = 'x'\n",
        "schema = 1\n[issues]\nitems_allow = [1]\n",
        "schema = 1\n[issues.status]\nactive = ['a', 2]\n",
        "schema = 1\n[issues.status]\ncheck = 'yes'\n",
        "schema = 1\n[issues.fields]\npriority = 'high'\n",
        "schema = 1\n[issues.fields]\nclosed_only_when_terminal = 1\n",
        "schema = 1\nissues = 'x'\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 3\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\nsections = 'no'\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\nextra_columns = { open = 'x' }\n",
        "schema = 1\n[freeze]\npaths = 'x'\n",
        "schema = 1\n[links]\nanchors = 'yes'\n",
    ],
)
def test_type_mismatches_are_errors(tmp_path, text):
    fail(tmp_path, text)


@pytest.mark.parametrize(
    "text",
    [
        "schema = 1\nlang = 'fr'\n",
        "schema = 1\n[issues]\nread = 'index'\n",
        "schema = 1\n[issues]\nuntracked = 'ignore'\n",
        "schema = 1\n[issues]\nuntracked_rows = 'ignore'\n",
        "schema = 1\n[issues]\nid_field = 'maybe'\n",
        "schema = 1\n[issues]\ntitle = 'h1'\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\nlink = 'both'\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\nempty = 'x'\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\nshow = ['rows']\n",
        "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\nlang = 'fr'\n",
        "schema = 1\n[freeze]\npaths = ['x']\nmode = 'loose'\n",
        "schema = 1\n[links]\nread = 'index'\n",
    ],
)
def test_enums_take_only_listed_values(tmp_path, text):
    assert "must be one of" in fail(tmp_path, text)


@pytest.mark.parametrize("marker", ["Issues", "a b", "a_b", "", "a:b"])
def test_marker_name_must_match_the_grammar(tmp_path, marker):
    text = f"schema = 1\n[issues.views.'R.md']\nmarker = '{marker}'\n"
    assert "[a-z0-9-]+" in fail(tmp_path, text)


def test_marker_is_required_for_a_view(tmp_path):
    assert "marker" in fail(tmp_path, "schema = 1\n[issues.views.'R.md']\n")


def test_freeze_paths_are_required(tmp_path):
    assert "paths" in fail(tmp_path, "schema = 1\n[freeze]\n")


def test_invalid_regular_expressions_are_errors(tmp_path):
    assert "regular expression" in fail(tmp_path, "schema = 1\n[issues]\nid_pattern = '('\n")
    assert "regular expression" in fail(
        tmp_path, "schema = 1\n[links]\nignore_targets = ['(']\n"
    )


def test_a_status_in_two_classes_is_an_error(tmp_path):
    text = "schema = 1\n[issues.status]\nactive = ['a']\ndeferred = ['a']\n"
    assert "more than one class" in fail(tmp_path, text)


def test_view_file_name_must_be_plain(tmp_path):
    assert "plain file name" in fail(tmp_path, "schema = 1\n[issues.views.'sub/R.md']\nmarker = 'm'\n")


def test_extra_columns_must_name_configured_statuses(tmp_path):
    text = "schema = 1\n[issues.views.'R.md']\nmarker = 'm'\nextra_columns = { bloked = ['x'] }\n"
    assert "bloked" in fail(tmp_path, text)


def test_configuration_errors_use_the_configured_language(tmp_path):
    message = fail(tmp_path, "schema = 1\nlang = 'ja'\n[issues]\nreed = 'x'\n")
    assert "未知のキー" in message


def test_root_defaults_to_the_git_top_level_of_the_current_directory(tmp_path):
    repo = Repo(tmp_path / "repo")
    nested = repo.root / "a" / "b"
    nested.mkdir(parents=True)
    assert resolve_root(None, nested) == repo.root.resolve()


def test_root_defaults_to_the_current_directory_outside_a_work_tree(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert resolve_root(None, plain) == plain.resolve()


def test_root_option_overrides_and_resolves_against_the_current_directory(tmp_path):
    (tmp_path / "x").mkdir()
    assert resolve_root("x", tmp_path) == (tmp_path / "x").resolve()
    assert resolve_root(str(tmp_path / "x"), Path("/")) == (tmp_path / "x").resolve()


def test_root_must_be_a_directory(tmp_path):
    with pytest.raises(ConfigError, match="--root"):
        resolve_root("absent", tmp_path)


def test_config_path_defaults_to_the_configuration_file_in_the_root(tmp_path):
    assert resolve_config_path(None, tmp_path, Path("/elsewhere")) == tmp_path / "mgtk-repo-utils.toml"
    assert resolve_config_path("alt.toml", tmp_path, tmp_path / "cwd") == (
        tmp_path / "cwd" / "alt.toml"
    ).resolve()


# [clone] (design section 13)

CLONE = """\
schema = 1
[clone]
roots = { work = "~/src", ops = "~/src/ops", env = "$EXAMPLE_ROOT" }
urls = ["git@github.com:example/*"]
[[clone.sources]]
file = "registry/repos.yaml"
entries = "teams[].services[]"
root = "ops"
url = "git@github.com:{repo}.git"
"""


def clone_fail(tmp_path: Path, old: str, new: str) -> str:
    assert old in CLONE
    return fail(tmp_path, CLONE.replace(old, new, 1))


def test_clone_source_defaults_are_exactly_the_documented_ones(tmp_path):
    clone = load_text(tmp_path, CLONE).table("clone")
    assert clone is not None
    assert clone.roots == {"work": "~/src", "ops": "~/src/ops", "env": "$EXAMPLE_ROOT"}
    assert clone.urls == ("git@github.com:example/*",)
    (source,) = clone.sources
    assert source.name == "clone.sources[0]"
    assert (source.file, source.entries, source.root) == (
        "registry/repos.yaml",
        "teams[].services[]",
        "ops",
    )
    assert (source.id, source.aliases, source.dir, source.local, source.exclude) == (
        "",
        "",
        "id",
        "",
        (),
    )


def test_a_file_without_a_clone_table_disables_the_clone_tools(tmp_path):
    assert load_text(tmp_path, "schema = 1\n").table("clone") is None


@pytest.mark.parametrize("key", ["roots", "urls", "sources"])
def test_roots_urls_and_sources_are_required(tmp_path, key):
    lines = [line for line in CLONE.splitlines() if not line.startswith(key)]
    if key == "sources":
        lines = lines[: lines.index("[[clone.sources]]")]
    assert f"`clone.{key}` is required" in fail(tmp_path, "\n".join(lines) + "\n")


@pytest.mark.parametrize("key", ["file", "entries", "root", "url"])
def test_a_source_requires_file_entries_root_and_url(tmp_path, key):
    text = "\n".join(line for line in CLONE.splitlines() if not line.startswith(f"{key} ="))
    assert f"`clone.sources[0].{key}` is required" in fail(tmp_path, text + "\n")


@pytest.mark.parametrize(
    "text",
    ["~/src/", "~/src//ops", "~/./src", "~/src/..", "src", "~", "$1ROOT", "${ROOT}", "$ROOT/x", "/a\tb", "~/a\u0085b", "/a\u2028b"],
)
def test_a_root_outside_the_three_forms_is_an_error(tmp_path, text):
    message = clone_fail(tmp_path, '"~/src/ops"', f'"{text}"')
    assert "`clone.roots.ops` must be `~/<path>`, `/<path>` or `$NAME` alone" in message


def test_a_root_name_must_be_a_plain_key(tmp_path):
    message = clone_fail(tmp_path, "work =", '"a b" =')
    assert "root name 'a b' in `clone.roots` must match [A-Za-z0-9_-]+" in message


@pytest.mark.parametrize("key", ["roots = {}", "urls = []"])
def test_empty_roots_or_urls_are_an_error(tmp_path, key):
    name = key.split(" ")[0]
    old = next(line for line in CLONE.splitlines() if line.startswith(name))
    assert f"`clone.{name}` must not be empty" in clone_fail(tmp_path, old, key)


@pytest.mark.parametrize(
    "pattern",
    [
        "git@github.com:example/*",
        "github.com:example/*",
        "ssh://git@github.com:22/example/*",
        "ssh://github.com/example/**",
        "file:///srv/example/*",
        "/srv/example/**",
    ],
)
def test_url_patterns_with_a_literal_transport_and_host_are_accepted(tmp_path, pattern):
    text = CLONE.replace('"git@github.com:example/*"', f'"{pattern}"', 1)
    assert load_text(tmp_path, text).table("clone").urls == (pattern,)


@pytest.mark.parametrize(
    "pattern",
    [
        "*@github.com:example/*",
        "git@*:example/*",
        "ssh://*/example/*",
        "ssh://github.com",
        "**",
        "example/*",
        "--template=example:*",
        "-oProxyCommand=x:*",
        "git@-oProxyCommand=x:*",
        "ssh://-oProxyCommand=x/*",
        "ssh://git@-oProxyCommand=x/*",
    ],
)
def test_url_patterns_without_a_literal_transport_and_host_are_an_error(tmp_path, pattern):
    message = clone_fail(tmp_path, '"git@github.com:example/*"', f'"{pattern}"')
    assert "must begin with a literal" in message


@pytest.mark.parametrize("file", ["/etc/repos.yaml", "../repos.yaml", "registry/../x.yaml", "a//b.yaml", ""])
def test_a_registry_file_must_stay_inside_the_repository(tmp_path, file):
    message = clone_fail(tmp_path, '"registry/repos.yaml"', f'"{file}"')
    assert "must be a path inside the repository" in message


@pytest.mark.parametrize("entries", ["teams[0]", "teams.[]", ".teams", "teams[].", "te ams", "teams[*]"])
def test_entries_are_keys_joined_by_dots_with_optional_brackets(tmp_path, entries):
    message = clone_fail(tmp_path, '"teams[].services[]"', f'"{entries}"')
    assert "must be keys joined by `.`" in message


def test_a_source_root_must_be_declared(tmp_path):
    assert "which is not in `clone.roots`" in clone_fail(tmp_path, 'root = "ops"', 'root = "other"')


def test_a_routed_root_table_names_this_copys_version(tmp_path):
    message = clone_fail(tmp_path, 'root = "ops"', 'root = { by = "class", map = { a = "work" } }')
    assert "as a table" in message and __version__ in message


@pytest.mark.parametrize("key", ['defaults = { class = "project" }', 'all = { status = ["active"] }'])
def test_keys_designed_for_later_are_rejected_with_this_copys_version(tmp_path, key):
    message = fail(tmp_path, CLONE + key + "\n")
    assert "unknown" in message and __version__ in message


@pytest.mark.parametrize("url", ["{}", "{a.b}", "{repo", "repo}", "{{repo}}", "x{repo}y}"])
def test_a_url_template_has_only_key_placeholders(tmp_path, url):
    message = clone_fail(tmp_path, '"git@github.com:{repo}.git"', f'"{url}"')
    assert "is not a valid template" in message


@pytest.mark.parametrize("key", ["id", "aliases", "local"])
def test_id_aliases_and_local_name_a_key_or_are_empty(tmp_path, key):
    assert load_text(tmp_path, CLONE + f'{key} = ""\n').table("clone") is not None
    assert f"`clone.sources[0].{key}` must name a key" in fail(tmp_path, CLONE + f'{key} = "a.b"\n')


def test_dir_is_id_or_url(tmp_path):
    assert load_text(tmp_path, CLONE + 'dir = "url"\n').table("clone").sources[0].dir == "url"
    assert "`clone.sources[0].dir` must be one of" in fail(tmp_path, CLONE + 'dir = "name"\n')


def test_sources_must_be_an_array_of_tables(tmp_path):
    text = CLONE.replace("[[clone.sources]]", "[clone.sources]", 1)
    assert "`clone.sources` must be an array of tables" in fail(tmp_path, text)
