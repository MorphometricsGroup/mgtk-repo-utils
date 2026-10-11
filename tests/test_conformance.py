# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path

import pytest

from support import Repo

SCRIPT = Path(__file__).resolve().parent / "conformance" / "frontmatter_vs_pyyaml.py"


@pytest.fixture(scope="module")
def conformance():
    pytest.importorskip("yaml")
    spec = importlib.util.spec_from_file_location("frontmatter_vs_pyyaml", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AGREEING = """\
---
id: 20260101_a
title: "Quoted | title"
status: open
priority: high
type: bug
created: 2026-01-01
closed:
closed_by:
blocked_by:
  - 20260102_b
  - "free text"
---
body
"""

FORMS = """\
---
id: 20260102_b
title: >-
  folded
  text
status: closed
created: 2026-01-02
closed: 2026-01-03
closed_by: 'someone'
blocked_by: [a, "b c"]
priority: 3
type: true
---
"""


def run(conformance, capsys, *dirs: Path) -> str:
    assert conformance.main([str(d) for d in dirs]) == 0
    return capsys.readouterr().out


def test_agreeing_files_report_no_mismatch(conformance, capsys, tmp_path):
    repo = Repo(tmp_path / "t", init=False)
    repo.write("issues/items/20260101_a.md", AGREEING)
    repo.write("issues/items/20260102_b.md", FORMS)
    repo.write("issues/README.md", "# not an issue\n")
    out = run(conformance, capsys, repo.root / "issues")
    assert out.splitlines()[:2] == ["files: 2", "mismatches: 0"]


def test_hash_truncation_is_a_rejection_not_a_mismatch(conformance, capsys, tmp_path):
    repo = Repo(tmp_path / "t", init=False)
    repo.write("issues/items/20260101_a.md", AGREEING.replace('"Quoted | title"', "X #7 more"))
    out = run(conformance, capsys, repo.root / "issues")
    assert "mismatches: 0" in out
    assert "rejections by rule: 1" in out
    assert "  plain-hash: 1" in out
    assert "20260101_a.md:3" in out


def test_colon_in_a_plain_scalar_is_a_pyyaml_error_and_a_rejection(conformance, capsys, tmp_path):
    repo = Repo(tmp_path / "t", init=False)
    repo.write("issues/items/20260101_a.md", AGREEING.replace('"Quoted | title"', "a: b"))
    out = run(conformance, capsys, repo.root / "issues")
    assert "pyyaml errors: 1" in out
    assert "  plain-colon: 1" in out


def test_a_real_disagreement_is_listed_per_key(conformance, capsys, tmp_path):
    repo = Repo(tmp_path / "t", init=False)
    # YAML 1.1 reads 0x10 as an integer; the reader keeps the text as written.
    repo.write("issues/items/20260101_a.md", AGREEING.replace("priority: high", "priority: 0x10"))
    out = run(conformance, capsys, repo.root / "issues")
    assert "mismatches: 1" in out
    assert "20260101_a.md:priority: reader '0x10' vs pyyaml '16'" in out


def test_flat_directories_are_read_too(conformance, capsys, tmp_path):
    repo = Repo(tmp_path / "t", init=False)
    repo.write("issues/20260101_a.md", AGREEING)
    assert "files: 1" in run(conformance, capsys, repo.root / "issues")


def test_leading_zeros_kept_by_the_reader_equal_the_pyyaml_integer(conformance, capsys, tmp_path):
    repo = Repo(tmp_path / "t", init=False)
    repo.write("issues/items/20260101_a.md", AGREEING.replace("id: 20260101_a", "id: 007"))
    out = run(conformance, capsys, repo.root / "issues")
    assert "mismatches: 0" in out


def test_an_integer_that_differs_from_the_reader_text_is_still_a_mismatch(conformance):
    assert conformance.same("001", 1, "1")
    assert not conformance.same("002", 1, "1")
    assert not conformance.same("1.0", 1, "1")
    assert not conformance.same("1", True, "true")  # a boolean is not an integer here
    assert not conformance.same("0x10", 16, "16")


def test_several_directories_are_read_together(conformance, capsys, tmp_path):
    first = Repo(tmp_path / "first", init=False)
    second = Repo(tmp_path / "second", init=False)
    first.write("issues/items/20260101_a.md", AGREEING)
    second.write("issues/20260102_b.md", FORMS)
    out = run(conformance, capsys, first.root / "issues", second.root / "issues")
    assert out.splitlines()[:2] == ["files: 2", "mismatches: 0"]
