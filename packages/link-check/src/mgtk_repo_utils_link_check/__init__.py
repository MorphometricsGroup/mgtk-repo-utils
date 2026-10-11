# SPDX-License-Identifier: Apache-2.0
"""link-check: relative Markdown links and heading anchors (design section 9)."""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from mgtk_repo_utils.config import Config, add_common_options, load_for_tool
from mgtk_repo_utils.files import list_files, list_untracked
from mgtk_repo_utils.patterns import glob_regex
from mgtk_repo_utils.report import ERROR, Report, ToolError, message, severity_for
from mgtk_repo_utils.slug import heading_slugs
from mgtk_repo_utils.tool import Tool

from .config import TABLE, LinksConfig
from .messages import MESSAGES

TOOL = "link-check"
MARKDOWN_SUFFIXES = (".md", ".markdown")
SCHEME = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*:")
FENCE = re.compile(r"(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
DEFINITION = re.compile(r" {0,3}\[(?!\^)((?:[^\[\]\\]|\\.)+)\]:[ \t]*(<[^<>]*>|\S+)")
HTML_ANCHOR = re.compile(
    r"<a\s[^>]*?\b(?:id|name)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))", re.IGNORECASE
)
BACKTICKS = re.compile(r"`+")
ESCAPED_PUNCTUATION = re.compile(r"\\([!-/:-@\[-`{-~])")
PUNCTUATION = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


@dataclass(frozen=True)
class Link:
    line: int
    target: str  # as written, without the `<>` of an angle-bracketed destination


def is_markdown(path: str) -> bool:
    return path.lower().endswith(MARKDOWN_SUFFIXES)


def frontmatter_end(lines: list[str]) -> int:
    """Index after the closing `---` of a frontmatter block; 0 when there is none."""
    if lines and lines[0].rstrip() == "---":
        for index in range(1, len(lines)):
            if lines[index].rstrip() == "---":
                return index + 1
    return 0


def outside_fences(lines: list[str]) -> list[tuple[int, str]]:
    """(index, line) for every line outside fenced code, fence lines excluded."""
    kept: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        match = FENCE.match(line.lstrip())
        if fence is None:
            if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
                fence = (match.group(1)[0], len(match.group(1)))
            else:
                kept.append((index, line))
        elif (
            match
            and match.group(1)[0] == fence[0]
            and len(match.group(1)) >= fence[1]
            and not match.group(2).strip()
        ):
            fence = None
    return kept


def mask_code_spans(text: str) -> str:
    """`text` with every inline code span replaced by spaces (line breaks kept)."""
    runs: list[tuple[int, int]] = []
    for match in BACKTICKS.finditer(text):
        start = match.start()
        slashes = len(text[:start]) - len(text[:start].rstrip("\\"))
        if slashes % 2:
            start += 1  # an escaped backtick is literal text
        if start < match.end():
            runs.append((start, match.end()))
    chars = list(text)
    i = 0
    while i < len(runs):
        length = runs[i][1] - runs[i][0]
        closer = next(
            (j for j in range(i + 1, len(runs)) if runs[j][1] - runs[j][0] == length), None
        )
        if closer is None:
            i += 1
            continue
        for k in range(runs[i][0], runs[closer][1]):
            if chars[k] != "\n":
                chars[k] = " "
        i = closer + 1
    return "".join(chars)


def _skip_space(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\n":
        i += 1
    return i


def _destination(text: str, i: int) -> tuple[str, int] | None:
    """Parse `dest "title")` after an opening parenthesis; the destination and the index after `)`."""
    n = len(text)
    i = _skip_space(text, i)
    start = i
    if i < n and text[i] == "<":
        i += 1
        while i < n and text[i] not in "<>\n":
            i += 2 if text[i] == "\\" else 1
        if i >= n or text[i] != ">":
            return None
        dest = text[start + 1 : i]
        i += 1
    else:
        depth = 0
        while i < n and text[i] not in " \t\n" and ord(text[i]) >= 0x20:
            char = text[i]
            if char == "\\" and i + 1 < n and text[i + 1] in PUNCTUATION:
                i += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            i += 1
        if depth:
            return None
        dest = text[start:i]
    after = _skip_space(text, i)
    if after < n and text[after] in "\"'(":
        close = ")" if text[after] == "(" else text[after]
        j = after + 1
        while j < n and text[j] != close:
            j += 2 if text[j] == "\\" else 1
        if j >= n:
            return None
        after = _skip_space(text, j + 1)
    if after < n and text[after] == ")":
        return dest, after + 1
    return None


def inline_destinations(text: str) -> list[tuple[int, str]]:
    """(index of the closing bracket, destination) of every inline link and image."""
    found: list[tuple[int, str]] = []
    opened: list[int] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "[":
            opened.append(i)
        elif char == "]" and opened:
            opened.pop()
            if text.startswith("(", i + 1):
                parsed = _destination(text, i + 2)
                if parsed is not None:
                    found.append((i, parsed[0]))
                    i = parsed[1]
                    continue
        i += 1
    return found


def extract_links(lines: list[str]) -> list[Link]:
    """Inline links, images and reference definitions outside fenced and inline code."""
    links: list[Link] = []
    blocks: list[list[tuple[int, str]]] = []
    for index, line in outside_fences(lines):
        if line.strip():
            if blocks and blocks[-1][-1][0] == index - 1:
                blocks[-1].append((index, line))
            else:
                blocks.append([(index, line)])
    for block in blocks:
        first = block[0][0]
        masked = mask_code_spans("\n".join(line for _, line in block))
        for position, target in inline_destinations(masked):
            links.append(Link(first + masked.count("\n", 0, position) + 1, target))
        for offset, line in enumerate(masked.split("\n")):
            match = DEFINITION.match(line)
            if match:
                target = match.group(2)
                links.append(Link(first + offset + 1, target[1:-1] if target[0] == "<" else target))
    return links


def anchors_of(lines: list[str]) -> set[str]:
    """Heading slugs (github-slugger) and `<a id>` / `<a name>` values of a Markdown file."""
    start = frontmatter_end(lines)
    kept = [(i, line) for i, line in outside_fences(lines) if i >= start]
    anchors = set(heading_slugs(line for _, line in kept if HEADING.match(line)))
    for _, line in kept:
        for match in HTML_ANCHOR.finditer(line):
            anchors.add(next(group for group in match.groups() if group is not None))
    return anchors


class _Run:
    def __init__(self, config: Config) -> None:
        cfg = config.table(TABLE.name)
        assert isinstance(cfg, LinksConfig)
        self.config = config
        self.cfg: LinksConfig = cfg
        self.root = config.root
        self.report = Report(TOOL, config.lang)
        self.excludes = [glob_regex(p) for p in self.cfg.exclude]
        self.ignores = [re.compile(p) for p in self.cfg.ignore_targets]
        self.untracked: set[str] = set()
        self.known: set[str] = set()
        self.directories: set[str] = {""}
        self._anchors: dict[str, set[str]] = {}

    def severity(self, path: str) -> str:
        """Severity of a problem in `path`: relaxed while the file is untracked."""
        return severity_for(self.cfg.untracked) if path in self.untracked else ERROR

    def excluded(self, path: str) -> bool:
        return any(pattern.fullmatch(path) for pattern in self.excludes)

    def execute(self) -> tuple[list[str], int]:
        cfg = self.cfg
        scan = list_files(self.root, cfg.read)
        self.known = set(scan.files)
        for path in self.known:
            parent = posixpath.dirname(path)
            while parent and parent not in self.directories:
                self.directories.add(parent)
                parent = posixpath.dirname(parent)
        self.untracked = set(list_untracked(self.root))
        documents = [p for p in scan.files if is_markdown(p) and not self.excluded(p)]
        for path in scan.missing:
            if is_markdown(path) and not self.excluded(path):
                self.report.warn("tracked-missing", path)
        checked = 0
        for path in documents:
            checked += self.check_file(path)
        summary = message(self.report.lang, "summary-links", files=len(documents), links=checked)
        return self.report.lines(summary), self.report.exit_code

    def anchors(self, path: str) -> set[str]:
        if path not in self._anchors:
            text = (self.root / path).read_bytes().decode("utf-8", errors="replace")
            self._anchors[path] = anchors_of(text.replace("\r\n", "\n").split("\n"))
        return self._anchors[path]

    def check_file(self, path: str) -> int:
        severity = self.severity(path)
        try:
            text = (self.root / path).read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            self.report.add(severity, "file-unreadable", path, detail=exc.reason)
            return 0
        links = extract_links(text.replace("\r\n", "\n").split("\n"))
        checked = 0
        for link in links:
            if SCHEME.match(link.target) or link.target.startswith("//"):
                continue
            if any(pattern.search(link.target) for pattern in self.ignores):
                continue
            checked += 1
            self.check_link(path, severity, link)
        return checked

    def check_link(self, path: str, severity: str, link: Link) -> None:
        target = ESCAPED_PUNCTUATION.sub(r"\1", link.target)
        location, _, fragment = target.partition("#")
        location = location.partition("?")[0]
        location, fragment = unquote(location), unquote(fragment)
        if not location:
            if self.cfg.anchors and fragment:
                self.check_anchor(path, severity, link, path, fragment)
            return
        if location.startswith("/"):
            joined = location.lstrip("/")
        else:
            joined = posixpath.join(posixpath.dirname(path), location)
        resolved = posixpath.normpath(joined)
        if resolved == "..":
            resolved = "../"
        if resolved.startswith("../"):
            self.report.add(severity, "link-outside", path, link.line, target=link.target)
            return
        resolved = "" if resolved == "." else resolved
        if resolved in self.directories:
            return
        if location.endswith("/") or resolved not in self.known:
            self.report.add(severity, "link-missing", path, link.line, target=link.target)
            return
        if self.cfg.anchors and fragment and is_markdown(resolved):
            self.check_anchor(path, severity, link, resolved, fragment)

    def check_anchor(
        self, path: str, severity: str, link: Link, target: str, fragment: str
    ) -> None:
        if fragment not in self.anchors(target):
            self.report.add(
                severity, "link-anchor-missing", path, link.line, fragment=fragment, file=target
            )


def run(config: Config) -> tuple[list[str], int]:
    """Check the configured links; returns the report lines and the exit code."""
    return _Run(config).execute()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgtk-repo-utils link-check",
        description="Check relative Markdown links, and with `anchors = true` their "
        "#fragments, against the listed files.",
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


TOOL_SPEC = Tool(name=TOOL, table=TABLE, messages=MESSAGES, main=main, check=run, check_order=30)
