# SPDX-License-Identifier: Apache-2.0
"""The `[freeze]` table (design sections 4 and 8)."""

from __future__ import annotations

from dataclasses import dataclass

from mgtk_repo_utils.config import ConfigError, Table
from mgtk_repo_utils.report import message
from mgtk_repo_utils.tool import TableSpec


@dataclass(frozen=True)
class FreezeConfig:
    paths: tuple[str, ...]
    allow: tuple[str, ...]
    mode: str
    reason: str



def _parse_freeze(table: Table, lang: str) -> FreezeConfig:
    if not table.has("paths"):
        raise ConfigError(message(table.lang, "cfg-required", name=table.dotted("paths")))
    return FreezeConfig(
        paths=table.strings("paths", ()),
        allow=table.strings("allow", ()),
        mode=table.enum("mode", "subset", ("subset", "exact")),
        reason=table.string("reason", ""),
    )




TABLE = TableSpec("freeze", ("paths", "allow", "mode", "reason"), _parse_freeze)
