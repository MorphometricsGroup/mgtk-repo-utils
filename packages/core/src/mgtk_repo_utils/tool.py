# SPDX-License-Identifier: Apache-2.0
"""The tool protocol and entry-point discovery (design section 3).

A tool distribution registers one `Tool` in the entry-point group
`mgtk_repo_utils.tools`. The core names no tool: the command discovers what is
installed, registers each tool's messages and configuration table, and
dispatches by name.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any

from . import report

GROUP = "mgtk_repo_utils.tools"


@dataclass(frozen=True)
class TableSpec:
    """A configuration table a tool declares: its name, allowed keys and parser.

    `parse` receives the table (a `config.Table`) and the file's language and
    returns the typed configuration the tool reads back with `Config.table()`.
    Two tools may share one spec (resolve and clone share `[clone]`).
    """

    name: str
    keys: tuple[str, ...] | None
    parse: Callable[[Any, str], object]


@dataclass(frozen=True)
class Tool:
    name: str  # the subcommand
    table: TableSpec | None  # the table that enables the tool; None = always available
    messages: Mapping[str, tuple[str, str]]  # message id -> (en, ja)
    main: Callable[[list[str], Path | None], int]  # argv after the tool name, cwd
    # The tool's step inside `check`, given the loaded Config: report lines and exit code.
    check: Callable[[Any], tuple[list[str], int]] | None = None
    check_order: int = 50  # `check` runs steps in ascending order, then by name
    distribution: str = field(default="", compare=False)  # filled at discovery


def discover(points: Iterable[EntryPoint] | None = None) -> dict[str, Tool]:
    """Load every registered tool, register its messages, and return them by name.

    Two distributions registering the same tool name is a usage error that
    names both (exit 2); it does not arise with one distribution installed.
    """
    found: dict[str, Tool] = {}
    for point in points if points is not None else entry_points(group=GROUP):
        loaded = point.load()
        distribution = point.dist.name if point.dist is not None else ""
        tool = Tool(
            name=loaded.name,
            table=loaded.table,
            messages=loaded.messages,
            main=loaded.main,
            check=loaded.check,
            check_order=loaded.check_order,
            distribution=distribution,
        )
        if tool.name in found:
            raise report.ToolError(
                report.message(
                    "en",
                    "tool-duplicate",
                    name=tool.name,
                    first=found[tool.name].distribution or "?",
                    second=distribution or "?",
                )
            )
        report.register(tool.messages)
        found[tool.name] = tool
    return found


def tables_of(tools: Mapping[str, Tool]) -> dict[str, TableSpec]:
    """The configuration tables the discovered tools declare, by table name."""
    tables: dict[str, TableSpec] = {}
    for tool in tools.values():
        if tool.table is not None:
            tables.setdefault(tool.table.name, tool.table)
    return tables
