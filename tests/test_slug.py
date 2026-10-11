# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest

from mgtk_repo_utils import slug as slug_module
from mgtk_repo_utils.slug import Slugger, heading_slugs, heading_text, slug

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_upstream_test_vectors_match_in_order_with_one_slugger():
    # Upstream runs the whole file through one slugger, so repeated inputs are numbered.
    fixtures = json.loads((FIXTURES / "github-slugger" / "fixtures.json").read_text("utf-8"))
    assert len(fixtures) >= 70
    slugger = Slugger()
    for entry in fixtures:
        assert slugger.slug(entry["input"]) == entry["expected"], entry["name"]


def test_synthetic_headings_match_the_upstream_oracle():
    expected = json.loads((FIXTURES / "slug-headings-synthetic.expected.json").read_text("utf-8"))
    lines = (FIXTURES / "slug-headings-synthetic.md").read_text("utf-8").split("\n")
    headings = [line for line in lines if line.startswith("#")]
    assert headings == [e["heading"] for e in expected]
    assert [heading_text(line) for line in headings] == [e["text"] for e in expected]
    assert heading_slugs(headings) == [e["slug"] for e in expected]


def test_synthetic_fixture_covers_the_character_classes_that_matter():
    texts = {
        e["text"]
        for e in json.loads((FIXTURES / "slug-headings-synthetic.expected.json").read_text("utf-8"))
    }
    for sample in (
        "ＡＢＣ １２３",
        "ＡＢＣ　１２３",
        "a b c",
        "①②③ 項目 ⑩",
        "🚀 launch 🎉",
        "a\tb\tc",
    ):
        assert sample in texts


def test_ascii_slug_behaviour():
    assert slug("Hello, World!") == "hello-world"
    assert slug("a  b") == "a--b"
    assert slug("snake_case and kebab-case") == "snake_case-and-kebab-case"
    assert slug("fooCamelCase", True) == "fooCamelCase"
    assert slug("") == ""


def test_full_width_letters_and_digits_are_kept_but_spaces_and_punctuation_are_deleted():
    assert slug("ＡＢＣ １２３") == "ａｂｃ-１２３"
    assert slug("ＡＢＣ　１２３") == "ａｂｃ１２３"
    assert slug("終わり．次へ") == "終わり次へ"


def test_non_string_input_gives_an_empty_slug():
    assert slug(1) == ""
    assert Slugger().slug(None) == ""


def test_repeated_slugs_are_numbered_and_taken_slugs_are_skipped():
    slugger = Slugger()
    assert [slugger.slug(v) for v in ("a", "a", "a-1", "a")] == ["a", "a-1", "a-1-1", "a-2"]


def test_slugger_reset_forgets_previous_slugs():
    slugger = Slugger()
    slugger.slug("a")
    slugger.reset()
    assert slugger.slug("a") == "a"


def test_removal_table_is_sorted_disjoint_and_inside_the_code_point_range():
    table = slug_module._REMOVED
    assert all(0 <= low <= high <= 0x10FFFF for low, high in table)
    assert all(table[i][1] + 1 < table[i + 1][0] for i in range(len(table) - 1))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ΑΣ", "ας"),  # final sigma, as JavaScript lowercases it
        ("ΑΣ Β", "ας-β"),
        ("İstanbul", "i̇stanbul"),
        ("ǅ", "ǆ"),
        ("ꟋꟜ", "ɤƛ"),  # letters of Unicode 16, absent from older Python data
    ],
)
def test_lowercasing_agrees_with_javascript(value, expected):
    assert slug(value) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("# Title", "Title"),
        ("###   Title  ", "Title"),
        ("## Title ##", "Title"),
        ("## C# language", "C# language"),
        ("##", ""),
        ("## **bold** and *italic*", "bold and italic"),
        ("## _emphasis_ and __strong__", "emphasis and strong"),
        ("## snake_case_name and _private", "snake_case_name and _private"),
        ("## `code` with `a_b*c`", "code with a_b*c"),
        ("## ``a ` b``", "a ` b"),
        ('## [link text](path/to.md#frag "title")', "link text"),
        ("## [`code link`](x.md)", "code link"),
        ("## ![alt text](img.png)", "alt text"),
        ("## [ref text][ref]", "ref text"),
        ("## [one](a) and [two](b)", "one and two"),
        ("## `[not](a link)`", "[not](a link)"),
        ("## a <kbd>Ctrl</kbd> key", "a Ctrl key"),
        ("## <https://example.com/x>", "<https://example.com/x>"),
        ("## escaped \\_not emphasis\\_", "escaped _not emphasis_"),
        ("## ＡＢＣ　", "ＡＢＣ　"),
    ],
)
def test_heading_text_removes_inline_markup(line, expected):
    assert heading_text(line) == expected


def test_heading_slugs_number_repeated_headings_of_one_document():
    assert heading_slugs(["## Intro", "## Intro", "### `Intro`"]) == ["intro", "intro-1", "intro-2"]
