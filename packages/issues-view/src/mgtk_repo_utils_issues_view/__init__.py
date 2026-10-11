# SPDX-License-Identifier: Apache-2.0
"""issues-view: layout and frontmatter checks, and generated views (design section 7)."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from mgtk_repo_utils import frontmatter
from mgtk_repo_utils.config import Config, add_common_options, load_for_tool
from mgtk_repo_utils.files import list_files, list_untracked
from mgtk_repo_utils.report import ERROR, WARNING, Report, ToolError, message, severity_for
from mgtk_repo_utils.tool import Tool

from .config import TABLE, IssuesConfig, ViewConfig
from .messages import MESSAGES

TOOL = "issues-view"


def issues_config(config: Config) -> IssuesConfig:
    cfg = config.table(TABLE.name)
    assert isinstance(cfg, IssuesConfig)
    return cfg
EMPTY_CELL = "—"
ASCII_SPACE_RUN = re.compile(r"[ \t\r\n\f\v]+")
FENCE = re.compile(r"(`{3,}|~{3,})")
# Shapes of the keys with a fixed meaning; any other key a view or on_terminal names is `any`.
KNOWN_SHAPES = {
    "status": frontmatter.SCALAR,
    "created": frontmatter.DATE,
    "id": frontmatter.SCALAR,
    "title": frontmatter.SCALAR,
    "priority": frontmatter.SCALAR,
    "type": frontmatter.SCALAR,
    "closed": frontmatter.DATE_OR_NULL,
    "blocked_by": frontmatter.LIST,
}
PSEUDO_COLUMNS = ("issue",)


@dataclass
class Item:
    id: str
    path: str  # relative to the root
    rel: str  # relative to the issues directory
    status: str
    title: str
    values: dict[str, frontmatter.Value]


@dataclass
class ViewFile:
    view: ViewConfig
    path: str
    lines: list[str]
    begin: int  # index of the BEGIN line
    end: int  # index of the END line
    body: list[str] = field(default_factory=list)

    @property
    def region(self) -> list[str]:
        return self.lines[self.begin + 1 : self.end]

    @property
    def stale(self) -> bool:
        return self.region != self.body

    def rendered(self) -> str:
        return "\n".join(self.lines[: self.begin + 1] + self.body + self.lines[self.end :])


def named_keys(cfg: IssuesConfig) -> set[str]:
    """Keys that on_terminal and the views refer to."""
    named = set(cfg.on_terminal)
    for view in cfg.views:
        named.update(view.columns, view.sort)
        for extra in view.extra_columns.values():
            named.update(extra)
        if view.group_by:
            named.add(view.group_by)
    return named - set(PSEUDO_COLUMNS)


def shapes_for(cfg: IssuesConfig) -> dict[str, str]:
    """The keys the configuration needs, with their shapes (design section 6)."""
    keys = {"status", "created", "id", "title"} | named_keys(cfg)
    if cfg.priority:
        keys.add("priority")
    if cfg.type:
        keys.add("type")
    if cfg.closed_only_when_terminal:
        keys.add("closed")
    return {key: KNOWN_SHAPES.get(key, frontmatter.ANY) for key in keys}


def first_heading(body: list[str]) -> str | None:
    """The first `# ` heading outside fenced code."""
    fence: tuple[str, int] | None = None
    for line in body:
        match = FENCE.match(line.lstrip())
        if match:
            marker = match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            continue
        if fence is None and line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return None


class _Run:
    def __init__(self, config: Config, write: bool) -> None:
        self.config = config
        self.cfg: IssuesConfig = issues_config(config)
        self.root = config.root
        self.write = write
        self.report = Report(TOOL, config.lang)
        base = self.cfg.dir.strip("/")
        self.base = "" if base in ("", ".") else base + "/"
        self.untracked: set[str] = set()

    def severity(self, path: str) -> str:
        """Severity of a problem in `path`: relaxed while the file is untracked."""
        return severity_for(self.cfg.untracked) if path in self.untracked else ERROR

    def execute(self) -> tuple[list[str], int]:
        cfg = self.cfg
        listing = list_files(self.root, cfg.read)
        for path in listing.missing:
            if path.startswith(self.base):
                self.report.warn("tracked-missing", path)
        self.untracked = set(list_untracked(self.root))
        candidates = sorted(set(listing.files) | self.untracked)
        item_paths = self.check_layout(candidates)
        read_set = set(listing.files)
        loaded = [self.load_item(p) for p in item_paths if p in read_set]
        items = [item for item in loaded if item is not None]
        views = self.prepare_views(items)
        written = 0
        diffs: list[str] = []
        if not self.report.problems:
            for view_file in views:
                if not view_file.stale:
                    continue
                if self.write:
                    (self.root / view_file.path).write_bytes(view_file.rendered().encode("utf-8"))
                    written += 1
                else:
                    self.report.error("view-stale", view_file.path, marker=view_file.view.marker)
                    diffs.extend(self.diff(view_file))
        counts = Counter(i.status for i in items)
        if written:
            summary = message(self.report.lang, "summary-wrote", written=written)
        else:
            summary = message(
                self.report.lang,
                "summary-issues",
                items=len(items),
                active=sum(counts[s] for s in cfg.active),
                deferred=sum(counts[s] for s in cfg.deferred),
                terminal=sum(counts[s] for s in cfg.terminal),
                views=len(cfg.views),
            )
        return self.report.lines(summary) + diffs, self.report.exit_code

    # layout

    def check_layout(self, candidates: list[str]) -> list[str]:
        cfg = self.cfg
        flat = cfg.items == ""
        allowed_top = {"README.md", cfg.template, *(v.file for v in cfg.views)}
        item_paths: list[str] = []
        for path in candidates:
            if not path.startswith(self.base):
                continue
            parts = path[len(self.base) :].split("/")
            severity = self.severity(path)
            if flat:
                if len(parts) > 1:
                    self.report.add(severity, "layout-subdir", path)
                elif parts[0] not in allowed_top and parts[0] not in cfg.items_allow:
                    self.item_name(path, parts[0], severity, item_paths)
            elif len(parts) == 1:
                if parts[0] not in allowed_top:
                    self.report.add(severity, "layout-stray", path, name=parts[0])
            elif parts[0] != cfg.items:
                self.report.add(severity, "layout-stray", path, name=parts[0] + "/")
            elif len(parts) > 2:
                self.report.add(severity, "layout-subdir", path)
            elif parts[1] not in cfg.items_allow:
                self.item_name(path, parts[1], severity, item_paths)
        return item_paths

    def item_name(self, path: str, name: str, severity: str, found: list[str]) -> None:
        if name.endswith(".md") and self.cfg.id_regex.fullmatch(name[: -len(".md")]):
            found.append(path)
        else:
            self.report.add(severity, "layout-item-name", path, name=name, pattern=self.cfg.id_pattern)

    # items

    def load_item(self, path: str) -> Item | None:
        cfg = self.cfg
        severity = self.severity(path)
        try:
            text = (self.root / path).read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            self.report.add(severity, "file-unreadable", path, detail=exc.reason)
            return None
        fm = frontmatter.parse(text, shapes_for(cfg))
        for problem in fm.problems:
            if problem.severity == frontmatter.WARNING:
                msg_id, level = f"fm-{problem.rule}-unread", WARNING
            else:
                msg_id, level = f"fm-{problem.rule}", severity
            self.report.add(level, msg_id, path, problem.line, key=problem.key)
        if not fm.present:
            return None
        rel = path[len(self.base) :]
        stem = Path(path).stem
        values = fm.values
        title = self.check_item(path, stem, fm, severity)
        status = values.get("status")
        if not isinstance(status, str) or not status:
            return None
        return Item(stem, path, rel, status, title, values)

    def check_item(self, path: str, stem: str, fm: frontmatter.Frontmatter, severity: str) -> str:
        """Run the frontmatter checks of section 7; returns the item's title."""
        cfg = self.cfg
        values, rejected = fm.values, fm.rejected
        known = cfg.active + cfg.deferred + cfg.terminal

        def fail(msg_id: str, **params: object) -> None:
            self.report.add(severity, msg_id, path, **params)

        if "id" not in rejected:
            ident = values.get("id")
            if not ident:
                if cfg.id_field == "required":
                    fail("id-missing", stem=stem)
            elif ident != stem:
                fail("id-mismatch", value=ident, stem=stem)

        title = values.get("title")
        title_text = title.strip() if isinstance(title, str) else ""
        if not title_text and "title" not in rejected:
            if cfg.title == "field-or-h1":
                title_text = first_heading(fm.body) or ""
            if not title_text:
                fail("title-missing-h1" if cfg.title == "field-or-h1" else "title-missing")

        if "created" not in rejected and values.get("created") is None:
            fail("created-missing")

        status = values.get("status")
        if "status" not in rejected:
            choices = ", ".join(known)
            if not status:
                fail("status-missing", choices=choices)
            elif status not in known:
                if cfg.status_check:
                    fail("status-unknown", value=status, choices=choices)
                else:
                    self.report.warn("status-other", path, value=status)

        for key, vocabulary in (("priority", cfg.priority), ("type", cfg.type)):
            if not vocabulary or key in rejected:
                continue
            value = values.get(key)
            choices = ", ".join(vocabulary)
            if not value:
                fail("field-missing", key=key, choices=choices)
            elif value not in vocabulary:
                fail("field-unknown", key=key, value=value, choices=choices)

        if isinstance(status, str) and status in cfg.terminal:
            for key in cfg.on_terminal:
                if key not in rejected and _is_empty(values.get(key)):
                    fail("terminal-field-missing", key=key, status=status)
        elif (
            isinstance(status, str)
            and cfg.closed_only_when_terminal
            and "closed" not in rejected
            and values.get("closed") is not None
        ):
            fail("closed-on-open", status=status)
        return title_text

    # views

    def prepare_views(self, items: list[Item]) -> list[ViewFile]:
        prepared: list[ViewFile] = []
        for view in self.cfg.views:
            view_file = self.read_view(view)
            if view_file is None:
                continue
            view_file.body = render_body(self.cfg, view, items)
            prepared.append(view_file)
            self.check_rows(view, items)
        return prepared

    def read_view(self, view: ViewConfig) -> ViewFile | None:
        path = self.base + view.file
        severity = self.severity(path)
        disk = self.root / path
        if not disk.is_file():
            self.report.add(severity, "view-missing", path, marker=view.marker)
            return None
        try:
            lines = disk.read_bytes().decode("utf-8").split("\n")
        except UnicodeDecodeError as exc:
            self.report.add(severity, "file-unreadable", path, detail=exc.reason)
            return None
        begin_line = f"<!-- BEGIN GENERATED: {view.marker} -->"
        end_line = f"<!-- END GENERATED: {view.marker} -->"
        begins = [i for i, line in enumerate(lines) if line.strip() == begin_line]
        ends = [i for i, line in enumerate(lines) if line.strip() == end_line]

        def fail(msg_id: str, **params: object) -> None:
            self.report.add(severity, msg_id, path, marker=view.marker, **params)

        if not begins:
            fail("marker-begin-missing")
            return None
        if len(begins) > 1:
            fail("marker-begin-multiple", count=len(begins), lines=_numbers(begins))
            return None
        begin = begins[0]
        before = [i for i in ends if i < begin]
        after = [i for i in ends if i > begin]
        for i in before:
            self.report.add(severity, "marker-end-before-begin", path, i + 1, marker=view.marker)
        if not after:
            fail("marker-end-missing")
        elif len(after) > 1:
            fail("marker-end-multiple", count=len(after), lines=_numbers(after))
        if before or len(after) != 1:
            return None
        return ViewFile(view, path, lines, begin, after[0])

    def check_rows(self, view: ViewConfig, items: list[Item]) -> None:
        if self.cfg.read != "worktree":
            return
        statuses = _shown_statuses(self.cfg, view)
        severity = severity_for(self.cfg.untracked_rows)
        for item in items:
            if item.status in statuses and item.path in self.untracked:
                self.report.add(
                    severity, "untracked-row", item.path, view=view.file, id=item.id
                )

    @staticmethod
    def diff(view_file: ViewFile) -> list[str]:
        return list(
            difflib.unified_diff(
                view_file.region,
                view_file.body,
                fromfile=f"{view_file.path} (current)",
                tofile=f"{view_file.path} (generated)",
                lineterm="",
            )
        )


def _numbers(indices: list[int]) -> str:
    return ", ".join(str(i + 1) for i in indices)


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not any(item.strip() for item in value)
    return False


# rendering


def _shown_statuses(cfg: IssuesConfig, view: ViewConfig) -> tuple[str, ...]:
    shown: tuple[str, ...] = ()
    if "active" in view.show:
        shown += cfg.active
    if "deferred" in view.show:
        shown += cfg.deferred
    return shown


def _clean(text: str) -> str:
    return ASCII_SPACE_RUN.sub(" ", text).strip()


def _escape(text: str) -> str:
    return text.replace("|", "\\|")


def _text(value: object) -> str:
    """A value as plain text; lists are comma-joined."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(_clean(item) for item in value if _clean(item))
    return _clean(str(value))


def _raw(item: Item, key: str) -> object:
    if key in ("issue", "id"):
        return item.id
    if key == "title":
        return item.title
    if key == "status":
        return item.status
    return item.values.get(key)


def _label(lang: str, column: str) -> str:
    return message(lang, "label-title") if column == "title" else column


def _cell(cfg: IssuesConfig, view: ViewConfig, item: Item, column: str) -> str:
    href = item.rel
    if column == "issue":
        return f"[`{item.id}`]({href})" if view.link == "issue" else f"`{item.id}`"
    value = _raw(item, column)
    if isinstance(value, list):
        parts = [_clean(part) for part in value if _clean(part)]
        text = "<br>".join(f"`{p}`" if cfg.id_regex.fullmatch(p) else p for p in parts)
    else:
        text = _text(value)
    text = _escape(text)
    if not text:
        return EMPTY_CELL
    if column == "title" and view.link == "title":
        return f"[{text}]({href})"
    return text


def _sort_key(cfg: IssuesConfig, view: ViewConfig, item: Item) -> tuple[object, ...]:
    parts: list[object] = []
    for key in view.sort:
        if key == "priority":
            if not cfg.priority:
                continue
            value = item.values.get("priority")
            if not value:
                parts.append((1, 0))
            else:
                known = cfg.priority.index(value) if value in cfg.priority else len(cfg.priority)
                parts.append((0, known))
            continue
        value = _raw(item, key)
        if isinstance(value, date):
            parts.append((0, value.toordinal()))
        elif _text(value):
            parts.append((0, _text(value)))
        else:
            parts.append((1, 0))
    parts.append(item.id)
    return tuple(parts)


def _counts_line(cfg: IssuesConfig, view: ViewConfig, items: list[Item]) -> str:
    lang = view.lang
    ja = lang == "ja"
    count = Counter(item.status for item in items)
    segments: list[str] = []
    for label_id, statuses in (
        ("count-active", cfg.active),
        ("count-deferred", cfg.deferred),
        ("count-terminal", cfg.terminal),
    ):
        if not statuses:
            continue
        total = sum(count[s] for s in statuses)
        segment = message(lang, label_id) + f" {total}" + (" 件" if ja else "")
        if len(statuses) > 1:
            detail = ("，" if ja else ", ").join(f"{s} {count[s]}" for s in statuses)
            segment += f"（{detail}）" if ja else f" ({detail})"
        segments.append(segment)
    if not cfg.status_check:
        known = set(cfg.active + cfg.deferred + cfg.terminal)
        other = sum(n for status, n in count.items() if status not in known)
        if other:
            segments.append(f"other {other}" + (" 件" if ja else ""))
    return ("／" if ja else " / ").join(segments)


def _table(cfg: IssuesConfig, view: ViewConfig, columns: list[str], items: list[Item]) -> list[str]:
    lines = [
        "| " + " | ".join(_label(view.lang, c) for c in columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for item in items:
        lines.append("| " + " | ".join(_cell(cfg, view, item, c) for c in columns) + " |")
    return lines


def _group_label(item: Item, key: str) -> str | None:
    return _text(_raw(item, key)) or None


def _section(cfg: IssuesConfig, view: ViewConfig, status: str, items: list[Item]) -> list[str]:
    columns = list(view.columns) + list(view.extra_columns.get(status, ()))
    lines = [f"### {status}", ""]
    if not view.group_by:
        return lines + _table(cfg, view, columns, items)
    groups: dict[str | None, list[Item]] = {}
    for item in items:
        groups.setdefault(_group_label(item, view.group_by), []).append(item)
    ordered: list[str | None] = sorted(label for label in groups if label is not None)
    if None in groups:
        ordered.append(None)
    blocks = []
    for label in ordered:
        heading = label if label is not None else message(view.lang, "none-group")
        blocks.append([f"#### {heading}", ""] + _table(cfg, view, columns, groups[label]))
    return lines + _join(blocks)


def _join(blocks: list[list[str]]) -> list[str]:
    lines: list[str] = []
    for block in blocks:
        if lines:
            lines.append("")
        lines.extend(block)
    return lines


def render_body(cfg: IssuesConfig, view: ViewConfig, items: list[Item]) -> list[str]:
    """The body lines between a view's marker lines (design section 7)."""
    counts = _counts_line(cfg, view, items)
    shown = _shown_statuses(cfg, view)
    by_status: dict[str, list[Item]] = {s: [] for s in shown}
    for item in sorted(items, key=lambda i: _sort_key(cfg, view, i)):
        if item.status in by_status:
            by_status[item.status].append(item)
    present = [s for s in shown if by_status[s]]
    if shown and not present:
        return [counts] if view.empty == "counts" else []
    blocks: list[list[str]] = []
    if "counts" in view.show:
        blocks.append([counts])
    if view.sections:
        blocks.extend(_section(cfg, view, s, by_status[s]) for s in present)
    elif present:
        columns = list(view.columns)
        if "status" not in columns:
            columns.insert(0, "status")
        for status in present:
            columns += [c for c in view.extra_columns.get(status, ()) if c not in columns]
        rows = [item for status in present for item in by_status[status]]
        blocks.append(_table(cfg, view, columns, rows))
    return _join(blocks)


def run(config: Config, write: bool = False) -> tuple[list[str], int]:
    """Check the issues and regenerate (`write`) or compare the views; report lines and exit code."""
    return _Run(config, write).execute()


# command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgtk-repo-utils issues-view",
        description="Check issue layout and frontmatter; regenerate or check the generated "
        "views. Without --write or --check the views are only compared, as with --check.",
    )
    add_common_options(parser)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="regenerate stale views (exit 0)")
    mode.add_argument(
        "--check", action="store_true", help="write nothing; print a diff of stale regions (exit 1)"
    )
    return parser


def main(argv: list[str], cwd: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_for_tool(args, TOOL, cwd or Path.cwd())
        lines, code = run(config, args.write)
    except ToolError as exc:
        print(f"mgtk-repo-utils: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return code


TOOL_SPEC = Tool(
    name=TOOL,
    table=TABLE,
    messages=MESSAGES,
    main=main,
    check=lambda config: run(config, write=False),
    check_order=10,
)
