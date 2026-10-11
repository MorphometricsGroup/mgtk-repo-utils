# SPDX-License-Identifier: Apache-2.0
"""check: run every installed tool whose table is present, then pin (design section 3)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from mgtk_repo_utils.config import Config, add_common_options, load, resolve_config_path, resolve_root
from mgtk_repo_utils.report import ToolError
from mgtk_repo_utils.tool import Tool, tables_of

from . import pin

PROG = "mgtk-repo-utils"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"{PROG} check",
        description="Run every installed tool whose table is present in the configuration "
        "(issues-view in --check mode, resolve --check for [clone]), then pin; a tool that "
        "stops with an error does not stop the others; exit with the highest exit code.",
    )
    add_common_options(parser)
    return parser


def steps_for(tools: dict[str, Tool], config: Config) -> list[tuple[str, Callable[[Config], tuple[list[str], int]]]]:
    """The `check` steps of the installed tools whose table the configuration has, in order."""
    ordered = sorted(tools.values(), key=lambda t: (t.check_order, t.name))
    return [
        (tool.name, tool.check)
        for tool in ordered
        if tool.check is not None and tool.table is not None and config.table(tool.table.name) is not None
    ]


def main(argv: list[str], tools: dict[str, Tool], cwd: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = cwd or Path.cwd()
    try:
        root = resolve_root(args.root, cwd)
        config = load(resolve_config_path(args.config, root, cwd), root, tables_of(tools))
    except ToolError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 2
    steps = [*steps_for(tools, config), (pin.TOOL, lambda c: pin.run(c.root, c.lang))]
    code = 0
    for name, step in steps:
        try:
            lines, step_code = step(config)
        except ToolError as exc:
            print(f"{PROG}: {name}: {exc}", file=sys.stderr, flush=True)
            code = 2
            continue
        # Flushed so a later step's error on standard error cannot overtake this report.
        print("\n".join(lines), flush=True)
        code = max(code, step_code)
    return code
