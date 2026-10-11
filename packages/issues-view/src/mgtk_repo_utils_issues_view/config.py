# SPDX-License-Identifier: Apache-2.0
"""The `[issues]` table (design sections 4 and 7)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from mgtk_repo_utils.config import READ_MODES, SEVERITIES, ConfigError, Table
from mgtk_repo_utils.report import LANGS, message
from mgtk_repo_utils.tool import TableSpec

SHOW_PARTS = ("counts", "active", "deferred")
DEFAULT_ID_PATTERN = r"\d{8}_[a-z0-9-]+"
MARKER_RE = re.compile(r"[a-z0-9-]+")


@dataclass(frozen=True)
class ViewConfig:
    file: str
    marker: str
    lang: str
    show: tuple[str, ...]
    sections: bool
    link: str
    columns: tuple[str, ...]
    extra_columns: dict[str, tuple[str, ...]]
    sort: tuple[str, ...]
    group_by: str
    empty: str


@dataclass(frozen=True)
class IssuesConfig:
    dir: str
    items: str
    template: str
    read: str
    untracked: str
    untracked_rows: str
    id_pattern: str
    id_regex: re.Pattern[str]
    id_field: str
    title: str
    items_allow: tuple[str, ...]
    active: tuple[str, ...]
    deferred: tuple[str, ...]
    terminal: tuple[str, ...]
    status_check: bool
    priority: tuple[str, ...]
    type: tuple[str, ...]
    on_terminal: tuple[str, ...]
    closed_only_when_terminal: bool
    views: tuple[ViewConfig, ...]



def _parse_issues(table: Table, lang: str) -> IssuesConfig:
    status = table.table("status", ("active", "deferred", "terminal", "check")) or Table(
        {}, "issues.status", lang, None
    )
    fields = table.table(
        "fields", ("priority", "type", "on_terminal", "closed_only_when_terminal")
    ) or Table({}, "issues.fields", lang, None)
    active = status.strings("active", ("in_progress", "blocked", "open"))
    deferred = status.strings("deferred", ("deferred",))
    terminal = status.strings("terminal", ("closed", "wont_fix"))
    known = active + deferred + terminal
    for value in known:
        if known.count(value) > 1:
            raise ConfigError(message(lang, "cfg-duplicate-status", value=value))
    pattern, id_regex = table.regex("id_pattern", DEFAULT_ID_PATTERN, re.ASCII)
    template = table.string("template", "_template.md")
    views_table = table.table("views", None)
    views: list[ViewConfig] = []
    if views_table is not None:
        for file_name, raw_view in views_table.raw.items():
            views.append(_parse_view(file_name, raw_view, views_table, lang, known))
    return IssuesConfig(
        dir=table.string("dir", "issues"),
        items=table.string("items", "items"),
        template=template,
        read=table.enum("read", "tracked", READ_MODES),
        untracked=table.enum("untracked", "warn", SEVERITIES),
        untracked_rows=table.enum("untracked_rows", "warn", SEVERITIES),
        id_pattern=pattern,
        id_regex=id_regex,
        id_field=table.enum("id_field", "required", ("required", "absent")),
        title=table.enum("title", "field", ("field", "field-or-h1")),
        items_allow=table.strings("items_allow", ()),
        active=active,
        deferred=deferred,
        terminal=terminal,
        status_check=status.boolean("check", True),
        priority=fields.strings("priority", ()),
        type=fields.strings("type", ()),
        on_terminal=fields.strings("on_terminal", ()),
        closed_only_when_terminal=fields.boolean("closed_only_when_terminal", False),
        views=tuple(views),
    )


def _parse_view(
    file_name: str, raw: object, views_table: Table, lang: str, known: tuple[str, ...]
) -> ViewConfig:
    if not file_name or "/" in file_name or "\\" in file_name:
        raise ConfigError(message(lang, "cfg-view-name", value=file_name))
    name = views_table.dotted(file_name)
    table = Table(
        raw,
        name,
        lang,
        (
            "marker",
            "lang",
            "show",
            "sections",
            "link",
            "columns",
            "extra_columns",
            "sort",
            "group_by",
            "empty",
        ),
    )
    if not table.has("marker"):
        raise ConfigError(message(lang, "cfg-required", name=table.dotted("marker")))
    marker = table.string("marker", "")
    if not MARKER_RE.fullmatch(marker):
        raise ConfigError(
            message(lang, "cfg-marker", name=table.dotted("marker"), value=repr(marker))
        )
    show = table.strings("show", SHOW_PARTS)
    for part in show:
        table.check_choice(part, table.dotted("show"), SHOW_PARTS)
    extra: dict[str, tuple[str, ...]] = {}
    extra_raw = table.table("extra_columns", None)
    if extra_raw is not None:
        for status_name in extra_raw.raw:
            if status_name not in known:
                raise ConfigError(
                    message(
                        lang,
                        "cfg-unknown-status",
                        name=extra_raw.dotted(status_name),
                        value=status_name,
                    )
                )
            extra[status_name] = extra_raw.strings(status_name, ())
    return ViewConfig(
        file=file_name,
        marker=marker,
        lang=table.enum("lang", lang, LANGS),
        show=show,
        sections=table.boolean("sections", True),
        link=table.enum("link", "issue", ("issue", "title")),
        columns=table.strings("columns", ("issue", "title", "created")),
        extra_columns=extra,
        sort=table.strings("sort", ("created",)),
        group_by=table.string("group_by", ""),
        empty=table.enum("empty", "nothing", ("nothing", "counts")),
    )




KEYS = (
    "dir",
    "items",
    "template",
    "read",
    "untracked",
    "untracked_rows",
    "id_pattern",
    "id_field",
    "title",
    "items_allow",
    "status",
    "fields",
    "views",
)
TABLE = TableSpec("issues", KEYS, _parse_issues)
