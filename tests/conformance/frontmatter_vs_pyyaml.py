# SPDX-License-Identifier: Apache-2.0
"""Conformance report: the strict frontmatter reader against PyYAML (design section 6).

usage: frontmatter_vs_pyyaml.py ISSUE_DIR [ISSUE_DIR ...]

Parses the frontmatter of every issue file under each directory (the directory
itself and its `items/` subdirectory) with the reader and with PyYAML's
safe_load, applies the design's normalisation to the PyYAML side, and prints
the number of files, per-key mismatches, and rejections counted by rule id.
The permitted differences are the reader's rejections and, for a scalar, a
PyYAML integer equal to the reader's text read as an integer (leading zeros are
kept on purpose); every other mismatch is a finding. Always exits 0: it is a report,
not a gate.

Needs PyYAML (a dependency of the clone tools; the frontmatter reader never imports it).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

from mgtk_repo_utils import frontmatter  # noqa: E402

SHAPES = {
    "id": frontmatter.SCALAR,
    "title": frontmatter.SCALAR,
    "status": frontmatter.SCALAR,
    "priority": frontmatter.SCALAR,
    "type": frontmatter.SCALAR,
    "created": frontmatter.DATE,
    "closed": frontmatter.DATE_OR_NULL,
    "closed_by": frontmatter.SCALAR,
    "blocked_by": frontmatter.LIST,
}
NOT_ISSUES = {"README.md", "TEMPLATE.md"}


def issue_files(directory: Path) -> list[Path]:
    found: list[Path] = []
    for folder in (directory, directory / "items"):
        if folder.is_dir():
            found.extend(
                p
                for p in sorted(folder.glob("*.md"))
                if p.name not in NOT_ISSUES and not p.name.startswith("_")
            )
    return found


def frontmatter_block(text: str) -> str | None:
    """The text between the delimiters, read the way the reader reads it."""
    lines = text.removeprefix("﻿").replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            return "\n".join(lines[1:index])
    return None


def scalar_text(value: object) -> object:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def normalise(shape: str, value: object) -> object:
    """PyYAML's value for a key, normalised by the key's shape as the design states."""
    if shape == frontmatter.LIST:
        if value is None:
            return []
        if isinstance(value, list):
            return [scalar_text(item) for item in value if item is not None]
        return value
    if shape in (frontmatter.DATE, frontmatter.DATE_OR_NULL):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return value
        return value
    return scalar_text(value)


def same(mine: object, raw: object, theirs: object) -> bool:
    """Equal after normalisation; a PyYAML integer also equals the reader's text read as an
    integer, because the reader keeps leading zeros (`001`) where PyYAML drops them."""
    if mine == theirs:
        return True
    if isinstance(raw, int) and not isinstance(raw, bool) and isinstance(mine, str):
        try:
            return int(mine) == raw
        except ValueError:
            return False
    return False


def main(argv: list[str]) -> int:
    directories = [Path(arg) for arg in argv]
    files = [path for directory in directories for path in issue_files(directory)]
    mismatches: list[str] = []
    yaml_errors: list[str] = []
    rejections: dict[str, list[str]] = defaultdict(list)
    warnings: dict[str, list[str]] = defaultdict(list)
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        read = frontmatter.parse(text, SHAPES)
        for problem in read.problems:
            target = rejections if problem.severity == frontmatter.ERROR else warnings
            target[problem.rule].append(f"{path}:{problem.line}")
        block = frontmatter_block(text)
        if block is None:
            continue
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError as exc:
            first_line = str(exc).strip().splitlines()[0]
            yaml_errors.append(f"{path}: {first_line}")
            continue
        if not isinstance(data, dict):
            data = {}
        for key, shape in SHAPES.items():
            if key in read.rejected:
                continue
            empty = [] if shape == frontmatter.LIST else None
            mine = read.values.get(key, empty)
            theirs = normalise(shape, data.get(key))
            if not same(mine, data.get(key), theirs):
                mismatches.append(f"{path}:{key}: reader {mine!r} vs pyyaml {theirs!r}")

    print(f"files: {len(files)}")
    print(f"mismatches: {len(mismatches)}")
    for line in mismatches:
        print(f"  {line}")
    print(f"pyyaml errors: {len(yaml_errors)}")
    for line in yaml_errors:
        print(f"  {line}")
    for title, table in (("rejections", rejections), ("warnings", warnings)):
        print(f"{title} by rule: {sum(len(v) for v in table.values())}")
        for rule in sorted(table):
            print(f"  {rule}: {len(table[rule])}")
            for where in table[rule]:
                print(f"    {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
