# SPDX-License-Identifier: Apache-2.0
"""resolve: an entry's destination and URL, and the static check (design sections 14 and 15)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mgtk_repo_utils.config import Config, add_common_options, load_for_tool
from mgtk_repo_utils.report import Report, ToolError, message

from . import registry
from .registry import Entry, clone_config

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


def _problem_lines(resolution: registry.Resolution, entry: Entry) -> list[str]:
    attached = resolution.problems_for(entry)
    return [problem.render() for problem in sorted(attached, key=lambda p: p.text)]


def _one(config: Config, resolution: registry.Resolution, name: str) -> list[Entry]:
    entry = resolution.find(name)
    if entry is None:
        raise ToolError(message(config.lang, "resolve-unknown", id=name))
    # An alias collision can exclude an entry; its problems say so, so they come first.
    if entry.excluded and not resolution.problems_for(entry):
        raise ToolError(
            message(config.lang, "resolve-excluded", id=name, source=entry.source.display)
        )
    return [entry]


def _set(config: Config, resolution: registry.Resolution, name: str) -> list[Entry]:
    if not resolution.declares_set(name):
        raise ToolError(
            message(
                config.lang,
                "resolve-set-unknown",
                name=name,
                known=registry.list_names(list(resolution.set_names), config.lang),
            )
        )
    return resolution.set_entries(name)


def run_entries(
    config: Config, args: argparse.Namespace
) -> tuple[list[tuple[Entry, str]], list[str]]:
    """The entries `args` selects with their destinations, and the problems that attach to them.

    An entry with a problem is not among the entries: its problems stand in for it, in order.
    """
    resolution = registry.load(config)
    problems: list[str] = []
    entries: list[Entry] = []
    if args.route is not None:
        entry, attached = registry.route(config, resolution, args.route[0], args.route[1:])
        if attached:
            problems = [p.render() for p in sorted(attached, key=lambda p: p.text)]
        else:
            entries.append(entry)
    else:
        if args.id is not None:
            selected = _one(config, resolution, args.id)
        else:
            selected = _set(config, resolution, "all" if args.all else args.set_name)
        for entry in selected:
            attached_lines = _problem_lines(resolution, entry)
            if attached_lines:
                problems.extend(attached_lines)
            else:
                entries.append(entry)
    roots = clone_config(config).roots
    return [
        (entry, registry.expand_destination(entry, roots, lang=config.lang)) for entry in entries
    ], problems


def run_root(config: Config, name: str) -> str:
    """The expanded path of the declared root `name`, without a trailing `/`."""
    roots = clone_config(config).roots
    if name not in roots:
        raise ToolError(
            message(
                config.lang,
                "resolve-root-unknown",
                name=name,
                known=registry.list_names(list(roots), config.lang),
            )
        )
    return registry.expand(roots[name], name, None, config.lang).rstrip("/") or "/"


def record(entry: Entry, destination: str) -> dict[str, object]:
    """The fields of an entry in `--format json` (design section 14)."""
    return {
        "id": entry.id,
        "destination": destination,
        "url": entry.url,
        "root": entry.root,
        "source": entry.source.display,
        "dir": entry.dir,
        "deviation": entry.deviation is not None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgtk-repo-utils resolve",
        description="Print `<id>\\t<destination>\\t<url>` for one entry of the registries "
        "declared in [clone], for every entry of a set (--set, --all), or for an entry the "
        "registry does not hold yet (--route); print a declared destination root expanded "
        "(--destination-root); or "
        "check every declaration with --check. Writes nothing and uses no network.",
    )
    parser.add_argument("id", nargs="?", help="an id or alias of an entry")
    parser.add_argument("--set", dest="set_name", metavar="NAME", help="every entry of a set")
    parser.add_argument("--all", action="store_true", help="every entry of the set `all`")
    parser.add_argument(
        "--route",
        nargs="+",
        metavar=("SOURCE", "KEY=VALUE"),
        help="where an entry the registry does not hold would be placed, and whether it "
        "would be a valid declaration; SOURCE is the `name` of a source",
    )
    parser.add_argument(
        "--destination-root",
        metavar="NAME",
        help="a declared destination root (`clone.roots`), printed expanded",
    )
    parser.add_argument(
        "--check", action="store_true", help="check the declarations instead of resolving"
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format of every form but --check (default: text)",
    )
    add_common_options(parser)
    return parser


def main(argv: list[str], cwd: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root_name = args.destination_root
    forms = [
        args.id is not None,
        args.set_name is not None,
        args.all,
        args.route is not None,
        root_name is not None,
        args.check,
    ]
    if sum(forms) != 1:
        parser.error(message("en", "resolve-usage"))
    if args.check and args.format != "text":
        parser.error(message("en", "resolve-format-check"))
    path = ""
    try:
        config = load_for_tool(args, TOOL, cwd or Path.cwd())
        if args.check:
            lines, code = run_check(config)
            print("\n".join(lines))
            return code
        entries: list[tuple[Entry, str]] = []
        problems: list[str] = []
        if root_name is not None:
            path = run_root(config, root_name)
        else:
            entries, problems = run_entries(config, args)
    except ToolError as exc:
        print(f"mgtk-repo-utils: {exc}", file=sys.stderr)
        return 2
    if problems:
        print("\n".join(problems), file=sys.stderr)
    if root_name is not None:
        print(json.dumps({"root": root_name, "path": path}) if args.format == "json" else path)
    elif args.format == "json":
        if not problems:  # a consumer that parses standard output never parses a partial array
            print(json.dumps([record(entry, destination) for entry, destination in entries]))
    else:
        for entry, destination in entries:
            print(f"{entry.id}\t{destination}\t{entry.url}")
    return 1 if problems else 0
