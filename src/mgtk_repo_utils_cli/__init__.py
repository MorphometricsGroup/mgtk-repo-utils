# SPDX-License-Identifier: Apache-2.0
"""The `mgtk-repo-utils` command: discovers the installed tools and dispatches (design section 3)."""

from __future__ import annotations

import sys
from pathlib import Path

from mgtk_repo_utils import __version__
from mgtk_repo_utils.report import ToolError
from mgtk_repo_utils.tool import Tool, discover

PROG = "mgtk-repo-utils"
BUILTIN = ("check", "pin", "tools")


def usage(tools: dict[str, Tool]) -> str:
    names = "|".join([*ordered(tools), *BUILTIN])
    return f"usage: {PROG} {{{names}}} [options]\n       {PROG} --version\n"


def ordered(tools: dict[str, Tool]) -> list[str]:
    return [t.name for t in sorted(tools.values(), key=lambda t: (t.check_order, t.name))]


def list_tools(tools: dict[str, Tool]) -> int:
    for tool in sorted(tools.values(), key=lambda t: (t.check_order, t.name)):
        table = f"[{tool.table.name}]" if tool.table is not None else "-"
        print(f"{tool.name}\t{table}\t{tool.distribution}")
    for name in BUILTIN:
        print(f"{name}\t-\t{PROG}")
    return 0


def main(argv: list[str] | None = None, cwd: Path | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        tools = discover()
    except ToolError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 2
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(usage(tools))
        return 0 if argv else 2
    name = argv[0]
    if name == "--version":
        print(f"{PROG} {__version__}")
        return 0
    if name == "tools":
        return list_tools(tools)
    if name == "check":
        from . import check

        return check.main(argv[1:], tools, cwd)
    if name == "pin":
        from . import pin

        return pin.main(argv[1:], cwd)
    if name in tools:
        return tools[name].main(argv[1:], cwd)
    sys.stderr.write(f"{PROG}: unknown tool {name!r}\n{usage(tools)}")
    return 2
