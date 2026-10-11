# SPDX-License-Identifier: Apache-2.0
from datetime import date

import pytest

from mgtk_repo_utils import frontmatter as fm
from mgtk_repo_utils.frontmatter import ANY, DATE, DATE_OR_NULL, LIST, SCALAR, RULES

SHAPES = {
    "id": SCALAR,
    "title": SCALAR,
    "status": SCALAR,
    "created": DATE,
    "closed": DATE_OR_NULL,
    "blocked_by": LIST,
    "extra": ANY,
}


def read(block: str, shapes=SHAPES) -> fm.Frontmatter:
    return fm.parse("---\n" + block + "\n---\nbody\n", shapes)


def rules(result: fm.Frontmatter) -> list[tuple[str, str]]:
    return [(p.rule, p.severity) for p in result.problems]


@pytest.mark.parametrize(
    ("block", "key", "expected"),
    [
        ("title: plain text", "title", "plain text"),
        ("title: a#b", "title", "a#b"),
        ("title: a\n  b\n  c", "title", "a b c"),
        ("title: a\n\n  b", "title", "a\nb"),
        ("title:\n  on the next line", "title", "on the next line"),
        ("title: 'it''s'", "title", "it's"),
        ('title: "a\\"b\\\\c\\nd\\te"', "title", 'a"b\\c\nd\te'),
        ('title: "a\n  b"', "title", "a b"),
        ('title: "a  \n\n  b"', "title", "a\nb"),
        ("title: 'a\n  b'", "title", "a b"),
        ("title: |\n  a\n  b\n", "title", "a\nb\n"),
        ("title: |-\n  a\n  b\n", "title", "a\nb"),
        ("title: >\n  a\n  b\n\n  c\n", "title", "a b\nc\n"),
        ("title: >-\n  a\n  b\n", "title", "a b"),
        ("title: >\n  a\n    more\n  b\n", "title", "a\n  more\nb\n"),
        ("title: |  # comment\n  a\n", "title", "a\n"),
        ("title: 123", "title", "123"),
        ("title: true", "title", "true"),
        ("title: 'null'", "title", "null"),
        ("title: null", "title", None),
        ("title: ~", "title", None),
        ("title:", "title", None),
        ("title: # only a comment", "title", None),
        ('title: "a" # trailing', "title", "a"),
        ("title: 'a'   # trailing", "title", "a"),
        ("title: ''", "title", ""),
        ("blocked_by: [a, b, \"c d\"]", "blocked_by", ["a", "b", "c d"]),
        ("blocked_by: []", "blocked_by", []),
        ("blocked_by: [a, ]", "blocked_by", ["a"]),
        ("blocked_by: [a] # trailing", "blocked_by", ["a"]),
        ("blocked_by: ['x, y', z]", "blocked_by", ["x, y", "z"]),
        ("blocked_by:\n  - a\n  - \"b c\"\n  - 'd'", "blocked_by", ["a", "b c", "d"]),
        ("blocked_by:\n  # first\n  - a\n  # between\n  - b\n", "blocked_by", ["a", "b"]),
        ("blocked_by:\n  - a\n  - b\n    c", "blocked_by", ["a", "b c"]),
        ("blocked_by:\n  # nothing here", "blocked_by", []),
        ("blocked_by:", "blocked_by", []),
        ("blocked_by: null", "blocked_by", []),
        ("blocked_by: ~", "blocked_by", []),
        ("blocked_by: # comment", "blocked_by", []),
        ("created: 2026-02-28", "created", date(2026, 2, 28)),
        ("created: '2026-02-28'", "created", date(2026, 2, 28)),
        ("closed: null", "closed", None),
        ("closed: 2024-02-29", "closed", date(2024, 2, 29)),
        ("extra: one", "extra", "one"),
        ("extra: [a, b]", "extra", ["a", "b"]),
        ("extra:\n  - a", "extra", ["a"]),
    ],
)
def test_accepted_forms_read_as_yaml_does(block, key, expected):
    result = read(block)
    assert result.problems == []
    assert result.values[key] == expected


def test_a_key_that_is_absent_is_not_in_values():
    assert "closed" not in read("title: x").values


def test_full_line_comments_are_ignored_anywhere():
    result = read("# top\ntitle: x\n  # indented comment\n# between\nstatus: open")
    assert result.problems == []
    assert result.values == {"title": "x", "status": "open"}


def test_bom_and_crlf_are_normalised():
    result = fm.parse("﻿---\r\ntitle: x\r\nblocked_by:\r\n  - a\r\n---\r\nbody\r\n", SHAPES)
    assert result.problems == []
    assert result.values == {"title": "x", "blocked_by": ["a"]}
    assert result.body == ["body", ""]


def test_body_and_line_numbers_follow_the_closing_delimiter():
    result = read("title: x\nstatus: open")
    assert result.body[0] == "body"
    assert result.body_line == 5


REJECTED = [
    ("missing", None, "title: x"),
    ("unterminated", None, None),
    ("plain-hash", 2, "title: X #7 more"),
    ("plain-hash", 2, "title: X\t#7"),
    ("plain-hash", 3, "title: X\n  continued #7"),
    ("plain-colon", 2, "title: a: b"),
    ("plain-colon", 2, "title: a:"),
    ("plain-indicator", 2, "title: @x"),
    ("plain-indicator", 2, "title: %x"),
    ("plain-indicator", 2, "title: `x"),
    ("anchor", 2, "title: &a x"),
    ("alias", 2, "title: *a"),
    ("tag", 2, "title: !!str x"),
    ("quote-trailing", 2, 'title: "a"#c'),
    ("quote-trailing", 2, "title: 'a' b"),
    ("tab-indent", 3, "blocked_by:\n\t- a"),
    ("tab-before-comment", 2, 'title: "a"\t# c'),
    ("tab-before-comment", 2, "blocked_by: [a]\t# c"),
    ("duplicate-key", 3, "title: a\ntitle: b"),
    ("nested-flow", 2, "blocked_by: [a, [b]]"),
    ("nested-flow", 3, "blocked_by:\n  - [a]"),
    ("flow-mapping", 2, "title: {a: b}"),
    ("list-item-not-indented", 3, "blocked_by:\n- a"),
    ("bad-date", 2, "created: 2026-02-30"),
    ("bad-date", 2, "created: tomorrow"),
    ("bad-date", 2, "created: 2026-1-1"),
    ("bad-date", 2, "closed: 2026-13-01"),
    ("list-expected", 2, "blocked_by: a"),
    ("scalar-expected", 2, "title: [a]"),
    ("scalar-expected", 3, "title:\n  - a"),
    ("unterminated-quote", 2, 'title: "abc'),
    ("unterminated-quote", 2, "title: 'abc\n  def"),
    ("bad-escape", 2, 'title: "caf\\u00e9"'),
    ("flow-unterminated", 2, "blocked_by: [a, b"),
    ("flow-trailing", 2, "blocked_by: [a] x"),
    ("flow-empty-item", 2, "blocked_by: [a,,b]"),
    ("block-scalar-indicator", 2, "title: |2\n  a"),
    ("block-scalar-indicator", 2, "title: |+\n  a"),
    ("syntax", 2, "just some words"),
    ("syntax", 2, "  stray: indentation"),
]


@pytest.mark.parametrize(("rule", "line", "block"), REJECTED)
def test_rejected_forms_name_their_rule_and_line(rule, line, block):
    if rule == "missing":
        result = fm.parse("title: x\n", SHAPES)
    elif rule == "unterminated":
        result = fm.parse("---\ntitle: x\n", SHAPES)
    else:
        result = read(block)
    matching = [p for p in result.problems if p.rule == rule]
    assert matching, f"{rule} not reported for {block!r}: {result.problems}"
    assert matching[0].severity == fm.ERROR
    if line is not None:
        assert matching[0].line == line


def test_every_rule_has_a_rejection_fixture():
    assert {rule for rule, _, _ in REJECTED} == set(RULES)


def test_a_rejected_key_is_reported_in_rejected_and_not_in_values():
    result = read("title: X #7\nstatus: open")
    assert result.rejected == {"title"}
    assert "title" not in result.values
    assert result.values["status"] == "open"


def test_duplicate_key_removes_the_value():
    result = read("title: a\ntitle: b")
    assert "title" in result.rejected
    assert "title" not in result.values


def test_unknown_keys_are_skipped_with_everything_indented_under_them():
    block = (
        "meta:\n  a: b: c\n  - x\n  nested:\n    deeper: [\n"
        "notes: |\n  text # with: odd things\n"
        "list:\n  - [a, [b]]\n"
        "status: open"
    )
    result = read(block)
    assert result.problems == []
    assert result.values == {"status": "open"}


def test_unknown_top_level_plain_scalar_with_hash_is_only_a_warning():
    result = read("closed_by: someone #1\nstatus: open")
    assert rules(result) == [("plain-hash", fm.WARNING)]
    assert result.problems[0].line == 2
    assert result.rejected == set()
    assert result.values["status"] == "open"


def test_unknown_scalar_with_quotes_or_brackets_is_not_interpreted():
    result = read("d: 'unterminated\ne: [x\nf: \"y\" z")
    assert result.problems == []


@pytest.mark.parametrize(
    ("block", "line"),
    [
        ("notes: a: b", 2),
        ("notes: a:", 2),
        ("notes: a:\tb", 2),
        ("notes: first\n  second: part", 3),
    ],
)
def test_unknown_top_level_plain_scalar_with_colon_is_only_a_warning(block, line):
    result = read(block + "\nstatus: open")
    assert rules(result) == [("plain-colon", fm.WARNING)]
    assert result.problems[0].line == line
    assert result.problems[0].key == "notes"
    assert result.rejected == set()
    assert result.values["status"] == "open"


def test_unknown_scalar_with_both_hash_and_colon_warns_once_per_rule():
    result = read("notes: a #b: c\n  more #d: e")
    assert rules(result) == [("plain-hash", fm.WARNING), ("plain-colon", fm.WARNING)]


def test_unknown_scalar_colon_inside_a_url_or_quotes_does_not_warn():
    result = read("home: http://example.com/a:b\nnote: \"a: b\"\nflow: [a: b]")
    assert result.problems == []


def test_unknown_key_with_tab_indentation_is_still_an_error():
    result = read("meta:\n\ta: b")
    assert ("tab-indent", fm.ERROR) in rules(result)


def test_duplicate_unknown_key_is_an_error():
    result = read("meta: a\nmeta: b")
    assert ("duplicate-key", fm.ERROR) in rules(result)


def test_only_requested_keys_are_read():
    result = fm.parse("---\nid: a\ntitle: t\n---\n", {"id": SCALAR})
    assert result.values == {"id": "a"}


def test_key_not_matching_the_key_shape_is_a_syntax_error():
    assert ("syntax", fm.ERROR) in rules(read("a.b: c"))
    assert ("syntax", fm.ERROR) in rules(read("a:b"))


def test_first_error_does_not_hide_later_keys():
    result = read("title: x #1\nstatus: open\ncreated: nope")
    assert [p.rule for p in result.problems] == ["plain-hash", "bad-date"]
    assert result.values["status"] == "open"
