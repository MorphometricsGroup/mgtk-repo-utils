# SPDX-License-Identifier: Apache-2.0
"""resolve: an entry's destination and URL, and the static check (design sections 14 and 15)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mgtk_repo_utils.config import Config, add_common_options, load_for_tool
from mgtk_repo_utils.report import Report, ToolError, message

from . import registry
from .registry import clone_config

TOOL = "resolve"


def run_check(config: Config, tool: str = TOOL) -> tuple[list[str], int]:
    """The static check of design section 15; returns the report lines and the exit code.

    `tool` names the command being run, for the remedy when PyYAML is missing.
    """
    resolution = registry.load(config, tool)
    report = Report(TOOL, config.lang)
    report.items.extend(resolution.problems)
    excluded = sum(1 for entry in resolution.entries if entry.excluded)
    summary = message(
        config.lang,
        "summary-resolve",
        entries=len(resolution.entries),
        sources=resolution.sources,
        excluded=excluded,
    )
    return report.lines(summary), report.exit_code


def run_one(config: Config, name: str) -> tuple[str | None, list[str]]:
    """The output line for one id or alias, or the rendered problems that attach to the entry."""
    resolution = registry.load(config)
    entry = resolution.find(name)
    if entry is None:
        raise ToolError(message(config.lang, "resolve-unknown", id=name))
    attached = resolution.problems_for(entry)
    # An alias collision can exclude an entry; its problems say so, so they come first.
    if entry.excluded and not attached:
        raise ToolError(
            message(config.lang, "resolve-excluded", id=name, source=entry.source.name)
        )
    if attached:
        return None, [problem.render() for problem in sorted(attached, key=lambda p: p.text)]
    assert entry.id is not None and entry.url is not None
    destination = registry.expand_destination(entry, clone_config(config).roots, lang=config.lang)
    return f"{entry.id}\t{destination}\t{entry.url}", []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgtk-repo-utils resolve",
        description="Print `<id>\\t<destination>\\t<url>` for one entry of the registries "
        "declared in [clone], or check every declaration with --check. Writes nothing and "
        "uses no network.",
    )
    parser.add_argument("id", nargs="?", help="an id or alias of an entry")
    parser.add_argument(
        "--check", action="store_true", help="check the declarations instead of resolving one id"
    )
    add_common_options(parser)
    return parser


def main(argv: list[str], cwd: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.id is not None) == args.check:
        parser.error(message("en", "resolve-usage"))
    try:
        config = load_for_tool(args, TOOL, cwd or Path.cwd())
        if args.check:
            lines, code = run_check(config)
            print("\n".join(lines))
            return code
        line, problems = run_one(config, args.id)
    except ToolError as exc:
        print(f"mgtk-repo-utils: {exc}", file=sys.stderr)
        return 2
    if line is None:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(line)
    return 0
