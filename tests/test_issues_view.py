# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from mgtk_repo_utils import __version__
from support import (
    BASIC_CONFIG,
    MARKERS,
    README,
    Repo,
    add_issue,
    basic_repo,
    issue_text,
    with_id,
)

BEGIN = "<!-- BEGIN GENERATED: issues-active -->"
END = "<!-- END GENERATED: issues-active -->"


def prepared(repo: Repo) -> Repo:
    repo.stage()
    return repo


def region(repo: Repo, rel: str = "issues/README.md") -> str:
    text = repo.read(rel)
    start = text.index(BEGIN) + len(BEGIN) + 1
    return text[start : text.index(END)]


# --- the three archetypal shapes, byte-exact -------------------------------------------------

EXPECTED_SECTIONS_EN = """\
active 2 (in_progress 0, blocked 1, open 1) / deferred 0 / done 1 (closed 1, wont_fix 0)

### blocked

| issue | title | priority | created |
|---|---|---|---|
| [`20260102_b`](items/20260102_b.md) | Beta | low | 2026-01-02 |

### open

| issue | title | priority | created |
|---|---|---|---|
| [`20260101_a`](items/20260101_a.md) | Alpha | high | 2026-01-03 |
"""


def fill_three(repo: Repo) -> None:
    add_issue(repo, "20260101_a", "open", priority="high", title="Alpha", created="2026-01-03")
    add_issue(repo, "20260102_b", "blocked", priority="low", title="Beta", created="2026-01-02")
    add_issue(repo, "20260103_c", "closed", priority="low", title="Gamma", created="2026-01-04")


def test_sections_view_region_is_byte_exact_in_english(tmp_path):
    repo = basic_repo(tmp_path)
    fill_three(repo)
    repo.stage()
    result = repo.run("issues-view", "--write")
    assert result.code == 0, result.out
    assert repo.read("issues/README.md") == (
        f"# Issues\n\n{BEGIN}\n{EXPECTED_SECTIONS_EN}{END}\n"
    )


def test_counts_line_in_japanese_matches_the_design_example(tmp_path):
    config = BASIC_CONFIG.replace('lang = "en"', 'lang = "ja"')
    repo = basic_repo(tmp_path, config)
    for n in range(4):
        add_issue(repo, f"2026010{n}_open", "open", priority="high")
    add_issue(repo, "20260110_blk", "blocked", priority="high")
    for n in range(4):
        add_issue(repo, f"2026011{n}_def", "deferred", priority="high")
    for n in range(8):
        add_issue(repo, f"2026012{n}_done", "closed", priority="high")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert region(repo).splitlines()[0] == (
        "active 5 件（in_progress 0，blocked 1，open 4）／deferred 4 件／終了 8 件（closed 8，wont_fix 0）"
    )


def test_counts_line_in_english_matches_the_design_example(tmp_path):
    repo = basic_repo(tmp_path)
    for n in range(4):
        add_issue(repo, f"2026010{n}_open", "open", priority="high")
    add_issue(repo, "20260110_blk", "blocked", priority="high")
    for n in range(4):
        add_issue(repo, f"2026011{n}_def", "deferred", priority="high")
    for n in range(8):
        add_issue(repo, f"2026012{n}_done", "closed", priority="high")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert region(repo).splitlines()[0] == (
        "active 5 (in_progress 0, blocked 1, open 4) / deferred 4 / done 8 (closed 8, wont_fix 0)"
    )


def test_view_language_overrides_the_top_level_language(tmp_path):
    config = BASIC_CONFIG + 'lang = "ja"\n'
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage()
    repo.run("issues-view", "--write")
    assert "件" in region(repo)
    assert "| issue | タイトル | priority | created |" in region(repo)


def test_class_without_configured_statuses_is_omitted_from_counts(tmp_path):
    config = BASIC_CONFIG.replace(
        "[issues]\n", "[issues]\n\n[issues.status]\ndeferred = []\nterminal = []\n", 1
    )
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage()
    repo.run("issues-view", "--write")
    assert region(repo).splitlines()[0] == "active 1 (in_progress 0, blocked 0, open 1)"


def test_single_table_with_title_link_and_status_column(tmp_path):
    config = BASIC_CONFIG.replace(
        'columns = ["issue", "title", "priority", "created"]',
        'sections = false\nlink = "title"\ncolumns = ["title", "priority"]',
    )
    repo = basic_repo(tmp_path, config)
    fill_three(repo)
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert region(repo).splitlines()[2:] == [
        "| status | title | priority |",
        "|---|---|---|",
        "| blocked | [Beta](items/20260102_b.md) | low |",
        "| open | [Alpha](items/20260101_a.md) | high |",
    ]


def test_single_table_puts_the_status_column_where_columns_names_it(tmp_path):
    config = BASIC_CONFIG.replace(
        'columns = ["issue", "title", "priority", "created"]',
        'sections = false\ncolumns = ["issue", "status", "title"]',
    )
    repo = basic_repo(tmp_path, config)
    fill_three(repo)
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert region(repo).splitlines()[2:] == [
        "| issue | status | title |",
        "|---|---|---|",
        "| [`20260102_b`](items/20260102_b.md) | blocked | Beta |",
        "| [`20260101_a`](items/20260101_a.md) | open | Alpha |",
    ]


def test_single_table_status_column_last_when_columns_ends_with_it(tmp_path):
    config = BASIC_CONFIG.replace(
        'columns = ["issue", "title", "priority", "created"]',
        'sections = false\ncolumns = ["title", "status"]',
    )
    repo = basic_repo(tmp_path, config)
    fill_three(repo)
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert region(repo).splitlines()[2:4] == ["| title | status |", "|---|---|"]


def test_group_by_makes_subsections_with_missing_value_last(tmp_path):
    config = BASIC_CONFIG.replace(
        'columns = ["issue", "title", "priority", "created"]',
        'group_by = "target"\ncolumns = ["issue", "title"]',
    ).replace('sort = ["priority", "created"]', 'sort = ["created"]')
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="high", title="A", target="zeta")
    add_issue(repo, "20260102_b", "open", priority="high", title="B")
    add_issue(repo, "20260103_c", "open", priority="high", title="C", target="alpha")
    add_issue(repo, "20260104_d", "open", priority="high", title="D", target="zeta")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert region(repo).splitlines()[2:] == [
        "### open",
        "",
        "#### alpha",
        "",
        "| issue | title |",
        "|---|---|",
        "| [`20260103_c`](items/20260103_c.md) | C |",
        "",
        "#### zeta",
        "",
        "| issue | title |",
        "|---|---|",
        "| [`20260101_a`](items/20260101_a.md) | A |",
        "| [`20260104_d`](items/20260104_d.md) | D |",
        "",
        "#### (none)",
        "",
        "| issue | title |",
        "|---|---|",
        "| [`20260102_b`](items/20260102_b.md) | B |",
    ]


def test_extra_columns_apply_per_status_and_render_id_lists_in_backticks(tmp_path):
    config = BASIC_CONFIG.replace(
        'sort = ["priority", "created"]',
        'sort = ["priority", "created"]\nextra_columns = { blocked = ["blocked_by"] }',
    ).replace('columns = ["issue", "title", "priority", "created"]', 'columns = ["issue"]')
    repo = basic_repo(tmp_path, config)
    add_issue(
        repo, "20260102_b", "blocked", priority="low", blocked_by='[20260101_a, "waiting | now"]'
    )
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    lines = region(repo).splitlines()
    assert "| issue | blocked_by |" in lines
    assert "| issue |" in lines
    assert "| [`20260102_b`](items/20260102_b.md) | `20260101_a`<br>waiting \\| now |" in lines


def test_sort_uses_vocabulary_order_then_created_then_id(tmp_path):
    repo = basic_repo(tmp_path)
    add_issue(repo, "20260105_e", "open", priority="low", created="2026-01-01")
    add_issue(repo, "20260101_a", "open", priority="low", created="2026-01-01")
    add_issue(repo, "20260109_i", "open", priority="high", created="2026-02-01")
    add_issue(repo, "20260102_b", "open", priority="low", created="2025-12-01")
    repo.stage()
    repo.run("issues-view", "--write")
    ids = [line.split("`")[1] for line in region(repo).splitlines() if line.startswith("| [")]
    assert ids == ["20260109_i", "20260102_b", "20260101_a", "20260105_e"]


def test_missing_sort_values_sort_last(tmp_path):
    config = (
        'schema = 1\n[issues]\n[issues.views."README.md"]\nmarker = "issues-active"\n'
        'columns = ["issue", "rank"]\nsort = ["rank"]\n'
    )
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open")
    add_issue(repo, "20260102_b", "open", rank="2")
    add_issue(repo, "20260103_c", "open", rank="1")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    ids = [line.split("`")[1] for line in region(repo).splitlines() if line.startswith("| [")]
    assert ids == ["20260103_c", "20260102_b", "20260101_a"]
    assert "| [`20260101_a`](items/20260101_a.md) | — |" in region(repo)


def test_priority_in_sort_is_ignored_when_the_vocabulary_is_empty(tmp_path):
    config = BASIC_CONFIG.replace('priority = ["high", "low"]', "priority = []")
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="low", created="2026-01-05")
    add_issue(repo, "20260102_b", "open", priority="high", created="2026-01-01")
    repo.stage()
    repo.run("issues-view", "--write")
    ids = [line.split("`")[1] for line in region(repo).splitlines() if line.startswith("| [")]
    assert ids == ["20260102_b", "20260101_a"]


def test_cells_collapse_whitespace_escape_pipes_and_dash_empty_values(tmp_path):
    config = BASIC_CONFIG.replace(
        'columns = ["issue", "title", "priority", "created"]',
        'columns = ["title", "target", "priority"]',
    )
    repo = basic_repo(tmp_path, config)
    add_issue(
        repo, "20260101_a", "open", priority="high", title='"a | b \\n  c\\t d  "'
    )
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert "| a \\| b c d | — | high |" in region(repo).splitlines()


def test_empty_region_for_no_items_is_the_two_marker_lines_only(tmp_path):
    repo = prepared(basic_repo(tmp_path))
    assert repo.run("issues-view", "--write").code == 0
    assert repo.read("issues/README.md") == README


def test_empty_counts_gives_only_the_counts_line(tmp_path):
    config = BASIC_CONFIG.replace(
        'sort = ["priority", "created"]', 'sort = ["priority", "created"]\nempty = "counts"'
    )
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "closed", priority="high")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert region(repo) == (
        "active 0 (in_progress 0, blocked 0, open 0) / deferred 0 / done 1 (closed 1, wont_fix 0)\n"
    )


def test_terminal_items_appear_only_in_counts(tmp_path):
    repo = basic_repo(tmp_path)
    add_issue(repo, "20260101_a", "open", priority="high")
    add_issue(repo, "20260102_b", "closed", priority="high")
    repo.stage()
    repo.run("issues-view", "--write")
    assert "20260102_b" not in region(repo)
    assert "done 1" in region(repo)


def test_show_selects_the_parts_of_the_body(tmp_path):
    config = BASIC_CONFIG.replace(
        'sort = ["priority", "created"]', 'sort = ["priority", "created"]\nshow = ["counts"]'
    )
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage()
    repo.run("issues-view", "--write")
    assert region(repo).count("\n") == 1
    assert "###" not in region(repo)


# --- region bytes ----------------------------------------------------------------------------


def test_adjacent_markers_with_zero_items_pass_check_and_are_unchanged_by_write(tmp_path):
    repo = prepared(basic_repo(tmp_path))
    before = repo.read("issues/README.md")
    check = repo.run("issues-view", "--check")
    assert check.code == 0, check.out
    assert repo.run("issues-view", "--write").code == 0
    assert repo.read("issues/README.md") == before


def test_everything_outside_the_marker_lines_is_preserved_byte_for_byte(tmp_path):
    readme = f"intro \r\n\t  \n  {BEGIN}  \nold\nlines\n\t{END}\t\n\nTail without newline"
    repo = basic_repo(tmp_path, readme=readme)
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    text = repo.read("issues/README.md")
    assert text.startswith(f"intro \r\n\t  \n  {BEGIN}  \n")
    assert text.endswith(f"\t{END}\t\n\nTail without newline")
    assert "old" not in text


def test_a_marker_quoted_inside_prose_is_not_a_marker(tmp_path):
    prose = f"Use `{BEGIN}` and {END} in text.\n"
    repo = basic_repo(tmp_path, readme=prose + MARKERS + prose)
    repo.stage()
    result = repo.run("issues-view", "--check")
    assert result.code == 0, result.out
    assert repo.run("issues-view", "--write").code == 0
    assert repo.read("issues/README.md") == prose + MARKERS + prose


def test_write_exits_zero_after_writing_and_check_then_passes(tmp_path):
    repo = basic_repo(tmp_path)
    fill_three(repo)
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    again = repo.run("issues-view", "--check")
    assert again.code == 0
    assert again.out.startswith("issues-view: ok")


def test_check_prints_a_unified_diff_of_the_region_and_writes_nothing(tmp_path):
    repo = basic_repo(tmp_path)
    fill_three(repo)
    repo.stage()
    result = repo.run("issues-view", "--check")
    assert result.code == 1
    assert "issues/README.md: generated region `issues-active` is out of date" in result.out
    assert "--- issues/README.md (current)" in result.out
    assert "+++ issues/README.md (generated)" in result.out
    assert "+### blocked" in result.out
    assert repo.read("issues/README.md") == README


def test_no_flag_compares_like_check(tmp_path):
    repo = basic_repo(tmp_path)
    fill_three(repo)
    repo.stage()
    assert repo.run("issues-view").code == 1
    assert repo.read("issues/README.md") == README


def test_no_view_is_written_while_a_problem_exists(tmp_path):
    repo = basic_repo(tmp_path)
    fill_three(repo)
    repo.write("issues/items/20260104_d.md", with_id("20260104_d", issue_text(created="nope")))
    repo.stage()
    result = repo.run("issues-view", "--write")
    assert result.code == 1
    assert repo.read("issues/README.md") == README


def test_write_and_check_are_mutually_exclusive(tmp_path):
    repo = prepared(basic_repo(tmp_path))
    result = repo.run("issues-view", "--write", "--check")
    assert result.code == 2
    assert "not allowed with" in result.err


@pytest.mark.parametrize(
    ("readme", "needle"),
    [
        ("# x\n", "no line `<!-- BEGIN GENERATED: issues-active -->`"),
        (f"{BEGIN}\n{END}\n{BEGIN}\n{END}\n", "2 BEGIN lines"),
        (f"{BEGIN}\n", "no line `<!-- END GENERATED: issues-active -->`"),
        (f"{BEGIN}\n{END}\n{END}\n", "2 END lines"),
        (f"{END}\n{BEGIN}\n{END}\n", "precedes the BEGIN line"),
        (f"{END}\n{BEGIN}\n", "precedes the BEGIN line"),
    ],
)
def test_marker_structure_errors(tmp_path, readme, needle):
    repo = prepared(basic_repo(tmp_path, readme=readme))
    result = repo.run("issues-view", "--check")
    assert result.code == 1
    assert needle in result.out
    assert repo.run("issues-view", "--write").code == 1
    assert repo.read("issues/README.md") == readme


def test_missing_view_file_is_an_error(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", BASIC_CONFIG)
    repo.stage()
    result = repo.run("issues-view", "--check")
    assert result.code == 1
    assert "issues/README.md: view file does not exist" in result.out


# --- layout ----------------------------------------------------------------------------------


def layout_repo(tmp_path: Path, config: str = BASIC_CONFIG) -> Repo:
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="high")
    return repo


def test_valid_layout_is_ok(tmp_path):
    repo = layout_repo(tmp_path)
    repo.write("issues/_template.md", "template")
    repo.write("issues/items/.gitkeep")
    repo.stage()
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\nitems_allow = [".gitkeep"]\n', 1)
    repo.write("mgtk-repo-utils.toml", config)
    repo.run("issues-view", "--write")
    result = repo.run("issues-view", "--check")
    assert result.code == 0, result.out


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        ("issues/notes.md", "`notes.md` is not allowed in the issues directory"),
        ("issues/20260101_x.md", "is not allowed in the issues directory"),
        ("issues/other/x.md", "`other/` is not allowed"),
        ("issues/items/readme.txt", "is not an item"),
        ("issues/items/bad_name.md", "is not an item"),
        ("issues/items/20260101_x.markdown", "is not an item"),
        ("issues/items/sub/20260101_x.md", "subdirectories are not allowed"),
    ],
)
def test_layout_violations_are_errors_when_tracked(tmp_path, path, needle):
    repo = layout_repo(tmp_path)
    repo.write(path, "x")
    repo.stage()
    repo.run("issues-view", "--write")
    result = repo.run("issues-view", "--check")
    assert result.code == 1
    assert f"{path}: " in result.out
    assert needle in result.out


def test_untracked_layout_violation_is_a_warning_by_default(tmp_path):
    repo = layout_repo(tmp_path)
    repo.stage()
    repo.run("issues-view", "--write")
    repo.write("issues/stray.md", "x")
    result = repo.run("issues-view", "--check")
    assert result.code == 0
    assert "issues-view: 1 warning(s)" in result.out
    assert "issues/stray.md: " in result.out


def test_untracked_layout_violation_is_an_error_when_configured(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\nuntracked = "error"\n', 1)
    repo = layout_repo(tmp_path, config)
    repo.stage()
    repo.run("issues-view", "--write")
    repo.write("issues/stray.md", "x")
    assert repo.run("issues-view", "--check").code == 1


def test_staging_a_misplaced_file_turns_the_warning_into_an_error(tmp_path):
    repo = layout_repo(tmp_path)
    repo.stage()
    repo.run("issues-view", "--write")
    repo.write("issues/stray.md", "x")
    assert repo.run("issues-view", "--check").code == 0
    repo.stage("issues/stray.md")
    assert repo.run("issues-view", "--check").code == 1


def test_template_and_registered_view_files_are_allowed(tmp_path):
    config = BASIC_CONFIG + (
        '[issues.views."BOARD.md"]\nmarker = "board"\n'
    )
    repo = layout_repo(tmp_path, config)
    repo.write("issues/_template.md", "t")
    repo.write("issues/BOARD.md", "<!-- BEGIN GENERATED: board -->\n<!-- END GENERATED: board -->\n")
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert "issues/BOARD.md" not in repo.run("issues-view", "--check").out


def test_flat_tracker_items_live_in_the_issues_directory(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\nitems = ""\n', 1)
    repo = basic_repo(tmp_path, config)
    repo.write("issues/20260101_a.md", with_id("20260101_a", issue_text(priority="high")))
    repo.write("issues/sub/x.md", "x")
    repo.stage()
    result = repo.run("issues-view", "--check")
    assert "issues/sub/x.md: subdirectories are not allowed" in result.out
    repo.run("issues-view", "--write")
    (repo.root / "issues" / "sub" / "x.md").unlink()
    repo.stage()
    assert repo.run("issues-view", "--write").code == 0
    assert "| [`20260101_a`](20260101_a.md) |" in region(repo)
    assert repo.run("issues-view", "--check").code == 0


def test_flat_tracker_rejects_a_non_item_file(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\nitems = ""\n', 1)
    repo = basic_repo(tmp_path, config)
    repo.write("issues/notes.txt", "x")
    repo.stage()
    assert "is not an item" in repo.run("issues-view", "--check").out


def test_tracked_path_missing_from_the_working_tree_is_skipped_with_a_warning(tmp_path):
    repo = layout_repo(tmp_path)
    add_issue(repo, "20260102_b", "open", priority="low")
    repo.stage()
    repo.run("issues-view", "--write")
    (repo.root / "issues/items/20260102_b.md").unlink()
    result = repo.run("issues-view", "--check")
    assert "issues/items/20260102_b.md: listed in the index but missing" in result.out
    assert result.code == 1  # the view still lists the deleted item, so it is stale


# --- frontmatter checks ----------------------------------------------------------------------


def one_item(tmp_path: Path, text: str, config: str = BASIC_CONFIG, stem: str = "20260101_a"):
    repo = basic_repo(tmp_path, config)
    repo.write(f"issues/items/{stem}.md", text)
    repo.stage()
    return repo, repo.run("issues-view", "--check")


def good(**kwargs: str) -> str:
    return with_id("20260101_a", issue_text(priority="high", **kwargs))


def test_reader_rejection_is_reported_with_path_line_and_remedy(tmp_path):
    _, result = one_item(tmp_path, good(title="X #7 and more"))
    assert result.code == 1
    assert "issues/items/20260101_a.md:3: unquoted value of `title` contains ` #`" in result.out
    assert "quote the value" in result.out


def test_missing_frontmatter_is_an_error(tmp_path):
    _, result = one_item(tmp_path, "# Just a heading\n")
    assert result.code == 1
    assert "no frontmatter block" in result.out


def test_id_must_equal_the_stem(tmp_path):
    text = good().replace("id: 20260101_a", "id: 20260101_zzz")
    _, result = one_item(tmp_path, text)
    assert "`id` is `20260101_zzz` but the file name is `20260101_a`" in result.out


def test_id_is_required_unless_configured_absent(tmp_path):
    text = issue_text(priority="high")
    _, result = one_item(tmp_path, text)
    assert "`id` is required; add `id: 20260101_a`" in result.out


def test_id_absent_mode_accepts_no_id_and_rejects_a_different_one(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\nid_field = "absent"\n', 1)
    repo, result = one_item(tmp_path, issue_text(priority="high"), config)
    assert "`id` is" not in result.out
    repo.write(
        "issues/items/20260101_a.md", with_id("other", issue_text(priority="high"))
    )
    repo.stage()
    assert "`id` is `other`" in repo.run("issues-view", "--check").out


def test_numbers_in_id_stay_strings_and_compare_with_the_stem(tmp_path):
    config = BASIC_CONFIG.replace(
        "[issues]\n", '[issues]\nid_pattern = "\\\\d+"\n', 1
    )
    text = "---\nid: 0042\ntitle: t\nstatus: open\ncreated: 2026-01-01\npriority: high\n---\n"
    _, result = one_item(tmp_path, text, config, stem="0042")
    assert "`id`" not in result.out


def test_title_is_required(tmp_path):
    _, result = one_item(tmp_path, with_id("20260101_a", issue_text(title=None, priority="high")))
    assert "no title; add a `title` field" in result.out


def test_title_can_come_from_the_first_heading_outside_fences(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\ntitle = "field-or-h1"\n', 1)
    body = "```\n# not a heading\n```\n\n# Real heading\n"
    text = with_id("20260101_a", issue_text(title=None, priority="high")).replace("Body.\n", body)
    repo, result = one_item(tmp_path, text, config)
    assert "no title" not in result.out
    repo.run("issues-view", "--write")
    config_cols = config.replace('"issue", "title"', '"title"')
    repo.write("mgtk-repo-utils.toml", config_cols)
    repo.run("issues-view", "--write")
    assert "| Real heading |" in region(repo)


def test_title_from_heading_fails_when_only_a_fenced_heading_exists(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\ntitle = "field-or-h1"\n', 1)
    text = with_id("20260101_a", issue_text(title=None, priority="high")).replace(
        "Body.\n", "~~~\n# fenced\n~~~\n"
    )
    _, result = one_item(tmp_path, text, config)
    assert "no title; add a `title` field or a `# ` heading" in result.out


def test_created_is_required_and_validated(tmp_path):
    _, result = one_item(tmp_path, with_id("20260101_a", issue_text(created=None, priority="high")))
    assert "`created` is required" in result.out
    _, result = one_item(tmp_path / "b", good(created="2026-02-30"))
    assert "`created` is not a valid date" in result.out


def test_unknown_status_is_an_error_with_known_values_listed(tmp_path):
    text = with_id("20260101_a", issue_text("weird", priority="high"))
    _, result = one_item(tmp_path, text)
    assert result.code == 1
    assert "status `weird` is not in [issues.status]" in result.out
    assert "in_progress, blocked, open, deferred, closed, wont_fix" in result.out


def test_unknown_status_with_check_off_warns_and_counts_as_other(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", "[issues]\n\n[issues.status]\ncheck = false\n", 1)
    repo, result = one_item(
        tmp_path, with_id("20260101_a", issue_text("weird", priority="high")), config
    )
    assert "status `weird` is not in [issues.status]; counted as `other`" in result.out
    add_issue(repo, "20260102_b", "open", priority="high")
    repo.stage()
    repo.run("issues-view", "--write")
    assert region(repo).splitlines()[0].endswith(" / other 1")
    assert repo.run("issues-view", "--check").code == 0


def test_status_is_required(tmp_path):
    text = "---\nid: 20260101_a\ntitle: t\ncreated: 2026-01-01\npriority: high\n---\n"
    _, result = one_item(tmp_path, text)
    assert "`status` is required" in result.out


def test_priority_and_type_are_checked_against_their_vocabularies(tmp_path):
    _, result = one_item(tmp_path, with_id("20260101_a", issue_text(priority="urgent")))
    assert "`priority` is `urgent`, not one of high, low" in result.out
    _, result = one_item(tmp_path / "b", with_id("20260101_a", issue_text()))
    assert "`priority` is required (one of high, low)" in result.out
    config = BASIC_CONFIG.replace("[issues.fields]\n", '[issues.fields]\ntype = ["bug"]\n', 1)
    _, result = one_item(tmp_path / "c", good(type="chore"), config)
    assert "`type` is `chore`" in result.out


def test_empty_vocabulary_means_not_checked(tmp_path):
    config = BASIC_CONFIG.replace('priority = ["high", "low"]', "priority = []")
    _, result = one_item(tmp_path, with_id("20260101_a", issue_text(priority="anything")), config)
    assert "`priority` is" not in result.out


TERMINAL_CONFIG = BASIC_CONFIG.replace(
    "[issues.fields]\n",
    '[issues.fields]\non_terminal = ["closed", "closed_by"]\nclosed_only_when_terminal = true\n',
    1,
)


def test_terminal_item_needs_every_on_terminal_key(tmp_path):
    text = with_id(
        "20260101_a", issue_text("closed", priority="high", closed="2026-02-01")
    )
    _, result = one_item(tmp_path, text, TERMINAL_CONFIG)
    assert "`closed_by` must be non-empty when the status is `closed`" in result.out
    assert "`closed` must be" not in result.out


def test_terminal_item_with_all_keys_passes(tmp_path):
    text = with_id(
        "20260101_a",
        issue_text("closed", priority="high", closed="2026-02-01", closed_by="someone"),
    )
    repo, _ = one_item(tmp_path, text, TERMINAL_CONFIG)
    repo.run("issues-view", "--write")
    assert repo.run("issues-view", "--check").code == 0


def test_closed_on_a_non_terminal_item_is_an_error(tmp_path):
    _, result = one_item(tmp_path, good(closed="2026-02-01"), TERMINAL_CONFIG)
    assert "`closed` is set but the status `open` is not terminal" in result.out


def test_closed_null_on_an_open_item_is_not_closed_present(tmp_path):
    repo, _ = one_item(tmp_path, good(closed="null"), TERMINAL_CONFIG)
    repo.run("issues-view", "--write")
    assert repo.run("issues-view", "--check").code == 0


def test_closed_with_an_invalid_date_is_reported_by_the_reader(tmp_path):
    text = with_id(
        "20260101_a", issue_text("closed", priority="high", closed="soon", closed_by="x")
    )
    _, result = one_item(tmp_path, text, TERMINAL_CONFIG)
    assert "`closed` is not a valid date" in result.out


def test_a_key_that_is_not_read_only_warns_about_a_hash(tmp_path):
    repo, result = one_item(tmp_path, good(closed_by="someone #1"))
    assert "issues/items/20260101_a.md:7: " in result.out
    assert "closed_by" in result.out
    assert "issues-view: 1 warning(s)" in result.out
    assert "problem(s)" in result.out  # the stale view is still a problem
    repo.run("issues-view", "--write")
    assert repo.run("issues-view", "--check").code == 0


def test_a_key_named_in_on_terminal_is_read_and_rejected(tmp_path):
    text = with_id(
        "20260101_a",
        issue_text("closed", priority="high", closed="2026-02-01", closed_by="someone #1"),
    )
    _, result = one_item(tmp_path, text, TERMINAL_CONFIG)
    assert result.code == 1
    assert "unquoted value of `closed_by`" in result.out
    assert "must be non-empty" not in result.out  # no cascade on a rejected key


def test_non_utf8_item_is_reported(tmp_path):
    repo = basic_repo(tmp_path)
    (repo.root / "issues/items").mkdir(parents=True)
    (repo.root / "issues/items/20260101_a.md").write_bytes(b"---\ntitle: \xff\n---\n")
    repo.stage()
    result = repo.run("issues-view", "--check")
    assert result.code == 1
    assert "cannot read the file as UTF-8" in result.out


def test_japanese_language_applies_to_problem_messages(tmp_path):
    config = BASIC_CONFIG.replace('lang = "en"', 'lang = "ja"')
    _, result = one_item(tmp_path, good(title="X #7"), config)
    assert "issues-view: 問題" in result.out
    assert "値を引用符で囲む" in result.out


# --- read scope and untracked severities ------------------------------------------------------


def test_tracked_mode_ignores_an_untracked_item_in_the_view(tmp_path):
    repo = basic_repo(tmp_path)
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage()
    add_issue(repo, "20260102_b", "open", priority="high")
    repo.run("issues-view", "--write")
    assert "20260102_b" not in region(repo)


def test_worktree_mode_includes_untracked_items_and_warns_about_the_row(tmp_path):
    config = BASIC_CONFIG.replace("[issues]\n", '[issues]\nread = "worktree"\n', 1)
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage()
    add_issue(repo, "20260102_b", "open", priority="high")
    result = repo.run("issues-view", "--write")
    assert result.code == 0
    assert "issues-view: 1 warning(s)" in result.out
    assert (
        "issues/items/20260102_b.md: view `README.md` lists `20260102_b`, which is not tracked"
        in result.out
    )
    assert "20260102_b" in region(repo)


def test_untracked_rows_can_be_an_error_and_then_nothing_is_written(tmp_path):
    config = BASIC_CONFIG.replace(
        "[issues]\n", '[issues]\nread = "worktree"\nuntracked_rows = "error"\n', 1
    )
    repo = basic_repo(tmp_path, config)
    add_issue(repo, "20260101_a", "open", priority="high")
    repo.stage("mgtk-repo-utils.toml", "issues/README.md")
    result = repo.run("issues-view", "--write")
    assert result.code == 1
    assert repo.read("issues/README.md") == README


def untracked_bad_item(tmp_path: Path, untracked: str) -> str:
    config = BASIC_CONFIG.replace(
        "[issues]\n", f'[issues]\nread = "worktree"\nuntracked = "{untracked}"\n', 1
    )
    repo = basic_repo(tmp_path, config)
    repo.stage()
    repo.write("issues/items/20260101_a.md", good(created="nope"))
    return repo.run("issues-view", "--check").out


def report_blocks(out: str) -> dict[str, list[str]]:
    """Problem lines grouped under their `problem(s)` / `warning(s)` header."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in out.splitlines():
        if line.startswith("issues-view: ") and line.endswith(("problem(s)", "warning(s)")):
            current = blocks.setdefault(line.rsplit(" ", 1)[1], [])
        elif line.startswith(("---", "+++", "@@", "+", "-", " ")):
            current = None
        elif current is not None:
            current.append(line)
    return blocks


def test_worktree_frontmatter_problem_in_an_untracked_item_is_a_warning_by_default(tmp_path):
    blocks = report_blocks(untracked_bad_item(tmp_path, "warn"))
    assert any("`created` is not a valid date" in line for line in blocks["warning(s)"])
    assert not any("`created`" in line for line in blocks.get("problem(s)", []))


def test_worktree_frontmatter_problem_in_an_untracked_item_is_an_error_when_configured(tmp_path):
    blocks = report_blocks(untracked_bad_item(tmp_path, "error"))
    assert any("`created` is not a valid date" in line for line in blocks["problem(s)"])


def test_filesystem_fallback_for_a_directory_nested_in_another_work_tree(tmp_path):
    outer = Repo(tmp_path / "outer")
    outer.write("x.md")
    outer.stage()
    inner = Repo(outer.root / "inner", init=False)
    inner.write("mgtk-repo-utils.toml", BASIC_CONFIG)
    inner.write("issues/README.md", README)
    add_issue(inner, "20260101_a", "open", priority="high")
    root = ("--root", str(inner.root))
    assert inner.run("issues-view", "--write", *root).code == 0
    assert "20260101_a" in region(inner)
    assert inner.run("issues-view", "--check", *root).code == 0


def test_filesystem_fallback_in_a_plain_directory(tmp_path):
    plain = Repo(tmp_path / "plain", init=False)
    plain.write("mgtk-repo-utils.toml", BASIC_CONFIG)
    plain.write("issues/README.md", README)
    add_issue(plain, "20260101_a", "open", priority="high")
    assert plain.run("issues-view", "--write").code == 0
    assert "20260101_a" in region(plain)


# --- command line ----------------------------------------------------------------------------


def test_missing_configuration_exits_two_on_stderr(tmp_path):
    repo = Repo(tmp_path / "repo")
    result = repo.run("issues-view")
    assert result.code == 2
    assert result.out == ""
    assert "configuration file not found" in result.err


def test_disabled_tool_exits_two(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", "schema = 1\n")
    result = repo.run("issues-view")
    assert result.code == 2
    assert "[issues] is absent" in result.err


def test_unknown_configuration_key_exits_two_naming_the_version(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", "schema = 1\n[issues]\nreed = 'x'\n")
    result = repo.run("issues-view")
    assert result.code == 2
    assert f"mgtk-repo-utils {__version__}" in result.err


def test_config_option_runs_with_an_alternative_file(tmp_path):
    repo = prepared(basic_repo(tmp_path))
    repo.write("mgtk-repo-utils.toml", "schema = 1\n")
    repo.write("alt.toml", BASIC_CONFIG)
    result = repo.run("issues-view", "--check", "--config", "alt.toml")
    assert result.code == 0, result.err + result.out


def test_root_option_runs_from_another_directory(tmp_path):
    repo = prepared(basic_repo(tmp_path))
    result = repo.run("issues-view", "--check", "--root", str(repo.root), cwd=tmp_path)
    assert result.code == 0, result.err + result.out


def test_root_defaults_to_the_git_top_level_when_run_from_a_subdirectory(tmp_path):
    repo = prepared(basic_repo(tmp_path))
    result = repo.run("issues-view", "--check", cwd=repo.root / "issues")
    assert result.code == 0, result.err + result.out


def test_success_prints_a_header_with_counts(tmp_path):
    repo = basic_repo(tmp_path)
    fill_three(repo)
    repo.stage()
    repo.run("issues-view", "--write")
    result = repo.run("issues-view", "--check")
    assert result.out == (
        "issues-view: ok (3 item(s): 2 active, 0 deferred, 1 done; 1 view(s) checked)\n"
    )


def test_unknown_key_with_a_colon_in_a_plain_scalar_is_a_warning_with_a_remedy(tmp_path):
    repo = basic_repo(tmp_path)
    add_issue(repo, "20260101_a", "open", priority="high", notes="see: below")
    repo.stage()
    result = repo.run("issues-view", "--write")
    assert result.code == 0
    assert "issues-view: 1 warning(s)" in result.out
    assert "20260101_a.md:" in result.out
    assert "the key is not read by the configured tools); quote the value" in result.out
