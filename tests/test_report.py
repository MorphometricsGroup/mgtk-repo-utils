# SPDX-License-Identifier: Apache-2.0
import string
from pathlib import Path

from mgtk_repo_utils import __version__
from mgtk_repo_utils.frontmatter import RULES
from mgtk_repo_utils.report import MESSAGES, Report, message, severity_for


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_every_message_has_both_languages_with_the_same_placeholders():
    for msg_id, (english, japanese) in MESSAGES.items():
        assert english and japanese, msg_id
        assert placeholders(english) == placeholders(japanese), msg_id


def test_every_reader_rule_has_a_message():
    for rule in RULES:
        assert f"fm-{rule}" in MESSAGES
    assert "fm-plain-hash-unread" in MESSAGES
    assert "fm-plain-colon-unread" in MESSAGES


def test_rejection_messages_name_their_remedy():
    assert "quote the value" in message("en", "fm-plain-hash", key="title")
    assert "値を引用符で囲む" in message("ja", "fm-plain-hash", key="title")
    assert "quote the value" in message("en", "fm-plain-colon", key="title")


def test_japanese_messages_use_ideographic_comma_and_full_stop_only():
    for msg_id, (_, japanese) in MESSAGES.items():
        assert "、" not in japanese and "。" not in japanese, msg_id


def test_section_sign_is_not_used_in_messages():
    assert all("§" not in text for pair in MESSAGES.values() for text in pair)


def test_version_is_the_latest_release_in_the_changelog():
    # release-please writes `## [X.Y.Z](url) (date)`; the first release heading is the current one.
    import re

    changelog = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = [line for line in changelog.splitlines() if line.startswith("## ")]
    assert headings
    found = re.search(r"\d+\.\d+\.\d+", headings[0])
    assert found and found.group(0) == __version__, headings[0]


def test_severity_names():
    assert severity_for("warn") == "warning"
    assert severity_for("error") == "error"


def test_report_with_problems_and_warnings():
    report = Report("tool", "en")
    report.error("id-missing", "b.md", 3, stem="b")
    report.error("id-missing", "a.md", None, stem="a")
    report.warn("status-other", "c.md", value="x")
    assert report.exit_code == 1
    assert report.lines() == [
        "tool: 2 problem(s)",
        "a.md: `id` is required; add `id: a`",
        "b.md:3: `id` is required; add `id: b`",
        "tool: 1 warning(s)",
        "c.md: status `x` is not in [issues.status]; counted as `other`",
    ]


def test_report_with_only_warnings_exits_zero_and_ends_with_ok():
    report = Report("tool", "en")
    report.warn("status-other", "c.md", value="x")
    assert report.exit_code == 0
    assert report.lines("3 item(s)")[-1] == "tool: ok (3 item(s))"


def test_clean_report_is_ok_in_japanese_headers():
    assert Report("tool", "ja").lines() == ["tool: ok"]
    report = Report("tool", "ja")
    report.error("id-missing", "a.md", stem="a")
    assert report.lines()[0] == "tool: 問題 1 件"
