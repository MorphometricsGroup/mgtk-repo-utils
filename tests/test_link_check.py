# SPDX-License-Identifier: Apache-2.0
import pytest

from mgtk_repo_utils_link_check import (
    anchors_of,
    extract_links,
    inline_destinations,
    mask_code_spans,
)
from mgtk_repo_utils.patterns import glob_regex
from support import Repo

CONFIG = "schema = 1\n[links]\n"
ANCHORS = "schema = 1\n[links]\nanchors = true\n"


def linked(tmp_path, files: dict[str, str], config: str = CONFIG, stage: bool = True) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.write("mgtk-repo-utils.toml", config)
    for name, text in files.items():
        repo.write(name, text)
    if stage:
        repo.stage()
    return repo


def problem_lines(out: str) -> list[str]:
    return [
        line for line in out.splitlines() if ".md" in line and not line.startswith("link-check:")
    ]


# --- what counts as a link ------------------------------------------------------------------


def test_existing_relative_links_pass_and_a_broken_one_is_reported_with_its_line(tmp_path):
    repo = linked(
        tmp_path,
        {
            "README.md": "# T\n\n[ok](docs/a.md) and [bad](docs/zzz.md)\n",
            "docs/a.md": "# A\n[up](../README.md)\n",
        },
    )
    result = repo.run("link-check")
    assert result.code == 1
    assert result.out.splitlines()[0] == "link-check: 1 problem(s)"
    assert result.out.splitlines()[1].startswith(
        "README.md:3: link target `docs/zzz.md` is not among the listed files"
    )


def test_success_summary_counts_files_and_checked_links(tmp_path):
    repo = linked(
        tmp_path, {"README.md": "[a](a.md) [x](https://example.invalid/)\n", "a.md": "text\n"}
    )
    result = repo.run("link-check")
    assert result.code == 0
    assert result.out.strip() == "link-check: ok (1 link(s) checked in 2 file(s))"


def test_images_and_reference_definitions_are_checked(tmp_path):
    text = '![alt](img/none.png)\n\n[ref]: docs/none.md\n[note]: <docs/gone two.md> "title"\n'
    result = linked(tmp_path, {"README.md": text}).run("link-check")
    assert result.code == 1
    assert "README.md:1: link target `img/none.png`" in result.out
    assert "README.md:3: link target `docs/none.md`" in result.out
    assert "README.md:4: link target `docs/gone two.md`" in result.out


def test_footnote_definitions_are_not_links(tmp_path):
    text = "Text[^1].\n\n[^1]: a note: see elsewhere\n"
    assert linked(tmp_path, {"README.md": text}).run("link-check").code == 0


def test_fenced_code_and_inline_code_are_skipped(tmp_path):
    text = (
        "`[a](none1.md)` and ``[b](none2.md)`` ok\n\n"
        "```\n[c](none3.md)\n```\n\n"
        "~~~sh\n[d](none4.md)\n~~~\n\n"
        "````\n```\n[e](none5.md)\n```\n````\n\n"
        "[real](none6.md)\n"
    )
    result = linked(tmp_path, {"README.md": text}).run("link-check")
    assert [line.split(":")[1] for line in problem_lines(result.out)] == ["17"]
    assert "none6.md" in result.out


def test_a_code_span_may_cross_a_line_break(tmp_path):
    text = "see `a\n[b](none.md)` here\n"
    assert linked(tmp_path, {"README.md": text}).run("link-check").code == 0


def test_targets_with_a_scheme_and_ignore_targets_are_skipped(tmp_path):
    text = (
        "[a](https://example.invalid/x) [b](mailto:someone@example.invalid) [c](HTTP://X.INVALID/)\n"
        "[d](//host.invalid/x) <https://example.invalid/auto> [e](${var}/x.md) [f](tmpl:none.md)\n"
    )
    config = CONFIG + "ignore_targets = ['^\\$', '^tmpl:']\n"
    assert linked(tmp_path, {"README.md": text}, config).run("link-check").code == 0


def test_ignore_targets_is_searched_anywhere_in_the_raw_target(tmp_path):
    config = CONFIG + "ignore_targets = ['generated']\n"
    text = "[a](docs/generated/x.md)\n[b](docs/other/x.md)\n"
    result = linked(tmp_path, {"README.md": text}, config).run("link-check")
    assert "docs/other/x.md" in result.out and "generated" not in result.out.replace("ignore", "")


def test_percent_encoded_paths_and_fragments_are_decoded(tmp_path):
    files = {
        "README.md": "[a](my%20doc.md#caf%C3%A9) [b](my%20doc.md#nope)\n",
        "my doc.md": "# Café\n",
    }
    result = linked(tmp_path, files, ANCHORS).run("link-check")
    assert result.code == 1
    assert "`#nope` in `my doc.md`" in result.out
    assert "caf" not in result.out.replace("my doc", "")


def test_destination_forms_title_angle_brackets_parentheses_query_and_root_relative(tmp_path):
    text = (
        '[a](a.md "title") [b](<sp ace.md>) [c](par(en).md) [d](a.md?plain=1) '
        "[e](/a.md) [f](docs/../a.md#) [g](./a.md)\n"
    )
    files = {"README.md": text, "a.md": "x\n", "sp ace.md": "x\n", "par(en).md": "x\n"}
    assert linked(tmp_path, files).run("link-check").code == 0


def test_a_link_that_leaves_the_repository_is_reported(tmp_path):
    result = linked(tmp_path, {"README.md": "[a](../outside.md) [b](..)\n"}).run("link-check")
    assert result.code == 1
    assert result.out.count("leaves the repository") == 2


def test_generated_view_regions_are_scanned_like_any_text(tmp_path):
    text = (
        "# Issues\n\n<!-- BEGIN GENERATED: issues-active -->\n| [`x`](items/gone.md) |\n"
        "<!-- END GENERATED: issues-active -->\n"
    )
    result = linked(tmp_path, {"issues/README.md": text}).run("link-check")
    assert "issues/README.md:4: link target `items/gone.md`" in result.out


def test_crlf_files_are_read(tmp_path):
    result = linked(tmp_path, {"README.md": "# T\r\n\r\n[bad](none.md)\r\n"}).run("link-check")
    assert "README.md:3:" in result.out


def test_only_markdown_files_are_scanned(tmp_path):
    files = {"notes.txt": "[bad](none.md)\n", "README.md": "ok\n"}
    assert linked(tmp_path, files).run("link-check").code == 0


# --- directories -----------------------------------------------------------------------------


def test_a_link_to_a_directory_resolves_with_and_without_a_trailing_slash(tmp_path):
    files = {
        "README.md": "[a](docs) [b](docs/) [c](docs/sub) [d](.) [e](./)\n",
        "docs/sub/x.md": "x\n",
    }
    assert linked(tmp_path, files).run("link-check").code == 0


def test_a_directory_with_no_listed_file_does_not_resolve(tmp_path):
    repo = linked(tmp_path, {"README.md": "[a](docs) [b](docs/)\n"}, stage=False)
    repo.stage("README.md", "mgtk-repo-utils.toml")
    repo.write("docs/untracked.md", "x\n")
    result = repo.run("link-check")
    assert result.code == 1
    assert result.out.count("is not among the listed files") == 2


def test_a_file_named_with_a_trailing_slash_is_not_a_directory(tmp_path):
    result = linked(tmp_path, {"README.md": "[a](a.md/)\n", "a.md": "x\n"}).run("link-check")
    assert result.code == 1


def test_anchors_are_not_checked_for_directories(tmp_path):
    files = {"README.md": "[a](docs/#nothing)\n", "docs/x.md": "x\n"}
    assert linked(tmp_path, files, ANCHORS).run("link-check").code == 0


# --- listing and severity --------------------------------------------------------------------


def test_a_link_to_an_untracked_file_fails_under_read_tracked(tmp_path):
    repo = linked(tmp_path, {"README.md": "[a](draft.md)\n"})
    repo.write("draft.md", "x\n")
    assert repo.run("link-check").code == 1


def test_a_link_to_an_untracked_file_resolves_under_read_worktree(tmp_path):
    repo = linked(tmp_path, {"README.md": "[a](draft.md)\n"}, CONFIG + 'read = "worktree"\n')
    repo.write("draft.md", "x\n")
    assert repo.run("link-check").code == 0


def test_a_link_to_an_ignored_file_fails_even_under_read_worktree(tmp_path):
    repo = linked(
        tmp_path,
        {"README.md": "[a](local.md)\n", ".gitignore": "local.md\n"},
        CONFIG + 'read = "worktree"\n',
    )
    repo.write("local.md", "x\n")
    assert repo.run("link-check").code == 1


def test_problems_in_an_untracked_file_are_warnings_by_default_under_read_worktree(tmp_path):
    repo = linked(tmp_path, {"README.md": "ok\n"}, CONFIG + 'read = "worktree"\n')
    repo.write("new.md", "[bad](none.md)\n")
    result = repo.run("link-check")
    assert result.code == 0
    assert result.out.splitlines()[0] == "link-check: 1 warning(s)"
    assert result.out.splitlines()[1].startswith("new.md:1:")


def test_untracked_error_severity_makes_them_failures(tmp_path):
    config = CONFIG + 'read = "worktree"\nuntracked = "error"\n'
    repo = linked(tmp_path, {"README.md": "ok\n"}, config)
    repo.write("new.md", "[bad](none.md)\n")
    assert repo.run("link-check").code == 1


def test_a_tracked_file_deleted_from_the_working_tree_warns_and_its_links_break(tmp_path):
    repo = linked(tmp_path, {"README.md": "[a](gone.md)\n", "gone.md": "x\n", "other.md": "x\n"})
    (repo.root / "gone.md").unlink()
    (repo.root / "other.md").unlink()
    result = repo.run("link-check")
    assert result.code == 1
    assert "gone.md: listed in the index but missing from the working tree" in result.out
    assert "README.md:1: link target `gone.md`" in result.out


def test_without_a_work_tree_the_filesystem_is_walked_and_dot_directories_are_skipped(tmp_path):
    repo = Repo(tmp_path / "plain", init=False)
    repo.write("mgtk-repo-utils.toml", CONFIG)
    repo.write("README.md", "[a](docs/a.md) [b](.hidden/x.md)\n")
    repo.write("docs/a.md", "x\n")
    repo.write(".hidden/x.md", "[c](none.md)\n")
    result = repo.run("link-check")
    assert result.code == 1
    assert "README.md:1: link target `.hidden/x.md`" in result.out
    assert "none.md" not in result.out


# --- exclude ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "path", "matches"),
    [
        ("archive/**", "archive/a.md", True),
        ("archive/**", "archive/deep/er/a.md", True),
        ("archive/**", "other/archive/a.md", False),
        ("*.draft.md", "x.draft.md", True),
        ("*.draft.md", "docs/x.draft.md", False),
        ("docs/?.md", "docs/a.md", True),
        ("docs/?.md", "docs/ab.md", False),
        ("docs/?.md", "docs//.md", False),
        ("**/skip.md", "skip.md", True),
        ("**/skip.md", "a/b/skip.md", True),
        ("**/skip.md", "a/b/notskip.md", False),
        ("docs/**/x.md", "docs/x.md", True),
        ("docs/**/x.md", "docs/a/b/x.md", True),
        ("a.b", "aXb", False),
    ],
)
def test_glob_semantics(pattern, path, matches):
    assert bool(glob_regex(pattern).fullmatch(path)) is matches


def test_excluded_files_are_not_scanned_but_remain_valid_targets(tmp_path):
    files = {
        "README.md": "[a](archive/old.md)\n",
        "archive/old.md": "[bad](none.md)\n",
        "drafts/x.draft.md": "[bad](none.md)\n",
    }
    config = CONFIG + 'exclude = ["archive/**", "drafts/*.draft.md"]\n'
    assert linked(tmp_path, files, config).run("link-check").code == 0


# --- anchors ---------------------------------------------------------------------------------


def test_fragments_are_not_checked_unless_anchors_is_true(tmp_path):
    files = {"README.md": "[a](a.md#nothing) [b](#nothing)\n", "a.md": "# A\n"}
    assert linked(tmp_path, files).run("link-check").code == 0


def test_heading_slugs_and_repeats_resolve(tmp_path):
    files = {
        "README.md": "[a](a.md#intro) [b](a.md#intro-1) [c](a.md#intro-2) [d](a.md#snake_case-api)\n",
        "a.md": "# Intro\n\n## Intro\n\n## `snake_case` API\n",
    }
    result = linked(tmp_path, files, ANCHORS).run("link-check")
    assert result.code == 1
    assert result.out.count("no heading or `<a id>`") == 1
    assert "`#intro-2` in `a.md`" in result.out


def test_same_file_fragments_are_checked(tmp_path):
    text = "# Top\n\n[ok](#top) [bad](#bottom)\n"
    result = linked(tmp_path, {"README.md": text}, ANCHORS).run("link-check")
    assert result.code == 1
    assert "`#bottom` in `README.md`" in result.out


def test_html_anchors_resolve(tmp_path):
    files = {
        "README.md": "[a](a.md#one) [b](a.md#two) [c](a.md#three)\n",
        "a.md": "<a id=\"one\"></a>\n<a name='two'></a>\n<A NAME=three>\n",
    }
    assert linked(tmp_path, files, ANCHORS).run("link-check").code == 0


def test_japanese_headings_with_full_width_punctuation_resolve(tmp_path):
    files = {
        "README.md": "[a](a.md#終わり次へ) [b](a.md#ａｂｃ-１２３) [c](a.md#宣言--観測)\n",
        "a.md": "## 終わり．次へ\n## ＡＢＣ １２３\n## 宣言 → 観測\n",
    }
    assert linked(tmp_path, files, ANCHORS).run("link-check").code == 0


def test_fragments_on_non_markdown_targets_are_not_checked(tmp_path):
    files = {"README.md": "[a](code.py#L10-L20)\n", "code.py": "x = 1\n"}
    assert linked(tmp_path, files, ANCHORS).run("link-check").code == 0


def test_headings_in_frontmatter_and_fenced_code_are_not_anchors(tmp_path):
    files = {
        "README.md": "[a](a.md#comment) [b](a.md#in-fence) [c](a.md#real)\n",
        "a.md": "---\n# comment\n---\n\n```\n# in fence\n```\n\n# Real\n",
    }
    result = linked(tmp_path, files, ANCHORS).run("link-check")
    assert result.out.count("no heading or `<a id>`") == 2
    assert "`#real`" not in result.out


def test_untracked_target_markdown_is_not_a_valid_anchor_target_under_read_tracked(tmp_path):
    repo = linked(tmp_path, {"README.md": "[a](draft.md#x)\n"}, ANCHORS)
    repo.write("draft.md", "# X\n")
    assert repo.run("link-check").code == 1


# --- output and configuration ----------------------------------------------------------------


def test_messages_come_from_the_japanese_catalogue(tmp_path):
    repo = linked(tmp_path, {"README.md": "[a](none.md)\n"}, 'lang = "ja"\n' + CONFIG)
    result = repo.run("link-check")
    assert result.out.splitlines()[0] == "link-check: 問題 1 件"
    assert "リンク先 `none.md` が対象ファイルの一覧にない" in result.out


def test_disabled_tool_exits_two(tmp_path):
    result = linked(tmp_path, {"README.md": "x\n"}, "schema = 1\n").run("link-check")
    assert result.code == 2
    assert "[links] is absent" in result.err


def test_an_invalid_ignore_regex_is_a_configuration_error(tmp_path):
    result = linked(tmp_path, {"README.md": "x\n"}, CONFIG + 'ignore_targets = ["("]\n').run(
        "link-check"
    )
    assert result.code == 2


# --- parsing units ---------------------------------------------------------------------------


def targets(text: str) -> list[tuple[int, str]]:
    return [(link.line, link.target) for link in extract_links(text.split("\n"))]


def test_nested_brackets_and_image_in_link(tmp_path):
    assert targets("[![alt](img.png)](page.md)") == [(1, "img.png"), (1, "page.md")]


def test_escaped_brackets_and_unbalanced_text_are_not_links():
    assert targets(r"\[a](b.md) [c] (d.md) [e]( f.md") == []


def test_inline_destinations_report_only_well_formed_links():
    assert [d for _, d in inline_destinations("[a](b.md) [c](d e.md) [f](g.md 'ttl')")] == [
        "b.md",
        "g.md",
    ]


def test_empty_destination_is_a_link_to_nothing():
    assert targets("[a]()") == [(1, "")]


def test_mask_code_spans_keeps_length_and_line_breaks():
    text = "a `b\nc` d ``e`` `unclosed"
    masked = mask_code_spans(text)
    assert len(masked) == len(text)
    assert masked.count("\n") == 1
    assert masked == "a " + "  \n  " + " d " + " " * 5 + " " + "`unclosed"


def test_escaped_backtick_does_not_open_a_code_span():
    assert mask_code_spans(r"\`a` [b](c.md)") == r"\`a` [b](c.md)"


def test_definition_needs_a_line_start_and_a_destination():
    assert targets("[a]: b.md\n  [c]: d.md\n    [e]: f.md\ntext [g]: h.md\n[i]:") == [
        (1, "b.md"),
        (2, "d.md"),
    ]


def test_anchors_of_collects_slugs_and_html_anchors():
    lines = ["# One", "", '<a id="x"></a>', "## One", "text", "#NotHeading"]
    assert anchors_of(lines) == {"one", "one-1", "x"}
