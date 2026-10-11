# SPDX-License-Identifier: Apache-2.0
"""The `[links]` table (design sections 4 and 9)."""

from __future__ import annotations

from dataclasses import dataclass

from mgtk_repo_utils.config import READ_MODES, SEVERITIES, Table
from mgtk_repo_utils.tool import TableSpec


@dataclass(frozen=True)
class LinksConfig:
    read: str
    untracked: str
    anchors: bool
    exclude: tuple[str, ...]
    ignore_targets: tuple[str, ...]



def _parse_links(table: Table, lang: str) -> LinksConfig:
    ignore = table.strings("ignore_targets", ())
    for pattern in ignore:
        table.compile(pattern, table.dotted("ignore_targets"))
    return LinksConfig(
        read=table.enum("read", "tracked", READ_MODES),
        untracked=table.enum("untracked", "warn", SEVERITIES),
        anchors=table.boolean("anchors", False),
        exclude=table.strings("exclude", ()),
        ignore_targets=ignore,
    )




TABLE = TableSpec(
    "links", ("read", "untracked", "anchors", "exclude", "ignore_targets"), _parse_links
)
