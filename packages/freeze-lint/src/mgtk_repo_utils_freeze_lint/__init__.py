# SPDX-License-Identifier: Apache-2.0
"""freeze-lint: tracked files under a path, checked against an allowlist (design section 8)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mgtk_repo_utils.config import Config, add_common_options, load_for_tool
from mgtk_repo_utils.files import tracked_under
from mgtk_repo_utils.report import Report, ToolError, message
from mgtk_repo_utils.tool import Tool

from .config import TABLE, FreezeConfig
from .messages import MESSAGES

TOOL = "freeze-lint"


def run(config: Config) -> tuple[list[str], int]:
    """Lint the configured paths; returns the report lines and the exit code."""
    cfg = config.table(TABLE.name)
    assert isinstance(cfg, FreezeConfig)
    report = Report(TOOL, config.lang)
    # The reason is the repository's own wording; it follows the message after a space.
    reason = f" {cfg.reason}" if cfg.reason else ""
    allowed = set(cfg.allow)
    owner: dict[str, str] = {}
    for frozen in cfg.paths:
        for tracked in tracked_under(config.root, frozen):
            owner.setdefault(tracked, frozen)
    for tracked, frozen in sorted(owner.items()):
        if tracked not in allowed:
            report.error("freeze-extra", tracked, frozen=frozen, reason=reason)
    if cfg.mode == "exact":
        for entry in cfg.allow:
            if entry not in owner:
                report.error("freeze-missing", entry, reason=reason)
    summary = message(
        config.lang, "summary-freeze", files=len(owner), paths=len(cfg.paths), mode=cfg.mode
    )
    return report.lines(summary), report.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgtk-repo-utils freeze-lint",
        description="Fail when a tracked file under a frozen path is not in the allowlist "
        "(and, in exact mode, when an allowlisted file is not tracked).",
    )
    add_common_options(parser)
    return parser


def main(argv: list[str], cwd: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_for_tool(args, TOOL, cwd or Path.cwd())
        lines, code = run(config)
    except ToolError as exc:
        print(f"mgtk-repo-utils: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return code


TOOL_SPEC = Tool(name=TOOL, table=TABLE, messages=MESSAGES, main=main, check=run, check_order=20)
