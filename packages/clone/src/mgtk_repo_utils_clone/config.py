# SPDX-License-Identifier: Apache-2.0
"""The `[clone]` table (design section 13)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mgtk_repo_utils.config import ConfigError, Table
from mgtk_repo_utils.report import message
from mgtk_repo_utils.tool import TableSpec

KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
VARIABLE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ENTRIES_RE = re.compile(r"[A-Za-z0-9_-]+(?:\[\])?(?:\.[A-Za-z0-9_-]+(?:\[\])?)*")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_-]+)\}")
SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
# C0 and C1 controls, and the line and paragraph separators: `str.splitlines()` breaks on them.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
SOURCE_KEYS = (
    "name",
    "file",
    "entries",
    "root",
    "url",
    "id",
    "aliases",
    "dir",
    "local",
    "exclude",
    "defaults",
    "sets",
)
ROOT_KEYS = ("by", "map")


@dataclass(frozen=True)
class RoutedRoot:
    """A root chosen by an entry's value: `root = { by = "<key>", map = { <value> = "<root>" } }`."""

    by: str  # key holding the value that selects the root
    map: dict[str, str]  # value -> a name in CloneConfig.roots


@dataclass(frozen=True)
class SourceConfig:
    name: str  # `clone.sources[<n>]`, for messages
    file: str
    entries: str
    root: str | RoutedRoot  # a name in CloneConfig.roots, or a routed root
    url: str  # template with `{key}` placeholders
    id: str  # key holding the id; "" = the URL's basename
    aliases: str  # key holding further ids; "" = none
    dir: str  # "id" | "url"
    local: str  # key holding a declared deviation; "" = none
    exclude: tuple[str, ...]
    declared: str = ""  # the `name` key; "" = none
    defaults: dict[str, str] = field(default_factory=dict)  # for `root.by` and `sets` only
    sets: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)  # set -> condition

    @property
    def display(self) -> str:
        """What reports call the source: its declared name, else its position."""
        return self.declared or self.name


@dataclass(frozen=True)
class CloneConfig:
    roots: dict[str, str]  # name -> declared path text, in file order
    urls: tuple[str, ...]
    sources: tuple[SourceConfig, ...]



def is_root_form(text: str) -> bool:
    """`~/<path>`, `/<path>` or `$NAME` alone, with no empty, `.` or `..` component."""
    if CONTROL_RE.search(text):
        return False
    if text.startswith("$"):
        return bool(VARIABLE_RE.fullmatch(text[1:]))
    if text.startswith("~/"):
        rest = text[2:]
    elif text.startswith("/"):
        rest = text[1:]
    else:
        return False
    return all(part not in ("", ".", "..") for part in rest.split("/"))


def has_literal_prefix(pattern: str) -> bool:
    """A `urls` pattern starts with a literal `<scheme>://<host>/`, `[<user>@]<host>:` or `/`.

    Neither the pattern nor its host may begin with `-`, so no URL it admits can read
    as an option (`--` before the URL is the second guard).
    """
    if pattern.startswith("-") or CONTROL_RE.search(pattern):
        return False
    scheme = SCHEME_RE.match(pattern)
    if scheme:
        host, slash, _ = pattern[scheme.end() :].partition("/")
        if not slash or "*" in host or "?" in host:
            return False
        return not host.rpartition("@")[2].startswith("-")
    if pattern.startswith("/"):
        return True
    head, colon, _ = pattern.partition(":")
    if not (colon and head) or any(c in head for c in "/*?"):
        return False
    return not head.rpartition("@")[2].startswith("-")


def _parse_clone(table: Table, lang: str) -> CloneConfig:
    lang = table.lang
    for key in ("roots", "urls", "sources"):
        if not table.has(key):
            raise ConfigError(message(lang, "cfg-required", name=table.dotted(key)))
    roots_table = table.table("roots", None)
    assert roots_table is not None
    roots: dict[str, str] = {}
    for name in roots_table.raw:
        if not KEY_RE.fullmatch(name):
            raise ConfigError(
                message(lang, "cfg-clone-root-name", name=table.dotted("roots"), value=repr(name))
            )
        text = roots_table.string(name, "")
        if not is_root_form(text):
            raise ConfigError(
                message(lang, "cfg-clone-root-form", name=roots_table.dotted(name), value=repr(text))
            )
        roots[name] = text
    if not roots:
        raise ConfigError(message(lang, "cfg-clone-empty", name=table.dotted("roots")))
    urls = table.strings("urls", ())
    if not urls:
        raise ConfigError(message(lang, "cfg-clone-empty", name=table.dotted("urls")))
    for pattern in urls:
        if not has_literal_prefix(pattern):
            raise ConfigError(
                message(lang, "cfg-clone-url-pattern", name=table.dotted("urls"), value=repr(pattern))
            )
    raw_sources = table.raw["sources"]
    if not isinstance(raw_sources, list) or not all(isinstance(s, dict) for s in raw_sources):
        raise table._type_error(table.dotted("sources"), "tables")
    if not raw_sources:
        raise ConfigError(message(lang, "cfg-clone-empty", name=table.dotted("sources")))
    sources = tuple(
        _parse_source(Table(raw, f"{table.dotted('sources')}[{index}]", lang, SOURCE_KEYS), roots)
        for index, raw in enumerate(raw_sources)
    )
    declared: dict[str, str] = {}
    for source in sources:
        if not source.declared:
            continue
        if source.declared in declared:
            raise ConfigError(
                message(
                    lang,
                    "cfg-clone-name-duplicate",
                    name=f"{source.name}.name",
                    value=repr(source.declared),
                    other=declared[source.declared],
                )
            )
        declared[source.declared] = source.name
    return CloneConfig(roots=roots, urls=urls, sources=sources)


def _parse_source(table: Table, roots: dict[str, str]) -> SourceConfig:
    lang = table.lang
    for key in ("file", "entries", "root", "url"):
        if not table.has(key):
            raise ConfigError(message(lang, "cfg-required", name=table.dotted(key)))
    file = table.string("file", "")
    parts = file.split("/")
    if not file or file.startswith("/") or "\\" in file or any(p in ("", ".", "..") for p in parts):
        raise ConfigError(message(lang, "cfg-clone-file", name=table.dotted("file"), value=repr(file)))
    entries = table.string("entries", "")
    if not ENTRIES_RE.fullmatch(entries):
        raise ConfigError(
            message(lang, "cfg-clone-entries", name=table.dotted("entries"), value=repr(entries))
        )
    root = _parse_root(table, roots)
    declared = table.string("name", "")
    if table.has("name") and not KEY_RE.fullmatch(declared):
        raise ConfigError(
            message(lang, "cfg-clone-name", name=table.dotted("name"), value=repr(declared))
        )
    url = table.string("url", "")
    outside = PLACEHOLDER_RE.sub("", url)
    if "{" in outside or "}" in outside:
        raise ConfigError(message(lang, "cfg-clone-template", name=table.dotted("url"), value=repr(url)))
    keys: dict[str, str] = {}
    for key in ("id", "aliases", "local"):
        value = table.string(key, "")
        if value and not KEY_RE.fullmatch(value):
            raise ConfigError(
                message(lang, "cfg-clone-key", name=table.dotted(key), value=repr(value))
            )
        keys[key] = value
    return SourceConfig(
        name=table.name,
        file=file,
        entries=entries,
        root=root,
        url=url,
        id=keys["id"],
        aliases=keys["aliases"],
        dir=table.enum("dir", "id", ("id", "url")),
        local=keys["local"],
        exclude=table.strings("exclude", ()),
        declared=declared,
        defaults=_parse_defaults(table),
        sets=_parse_sets(table),
    )


def _declared_root(name: str, value: str, roots: dict[str, str], lang: str) -> str:
    if value not in roots:
        raise ConfigError(message(lang, "cfg-clone-root-unknown", name=name, value=repr(value)))
    return value


def _parse_root(table: Table, roots: dict[str, str]) -> str | RoutedRoot:
    lang = table.lang
    if not isinstance(table.raw["root"], dict):
        return _declared_root(table.dotted("root"), table.string("root", ""), roots, lang)
    routed = table.table("root", ROOT_KEYS)
    assert routed is not None
    for key in ROOT_KEYS:
        if not routed.has(key):
            raise ConfigError(message(lang, "cfg-required", name=routed.dotted(key)))
    by = routed.string("by", "")
    if not KEY_RE.fullmatch(by):
        raise ConfigError(message(lang, "cfg-clone-by", name=routed.dotted("by"), value=repr(by)))
    mapping_table = routed.table("map", None)
    assert mapping_table is not None
    if not mapping_table.raw:
        raise ConfigError(message(lang, "cfg-clone-empty", name=routed.dotted("map")))
    mapping = {
        value: _declared_root(
            mapping_table.dotted(value), mapping_table.string(value, ""), roots, lang
        )
        for value in mapping_table.raw
    }
    return RoutedRoot(by=by, map=mapping)


def _parse_defaults(table: Table) -> dict[str, str]:
    defaults = table.table("defaults", None)
    if defaults is None:
        return {}
    return {key: defaults.string(key, "") for key in defaults.raw}


def _parse_sets(table: Table) -> dict[str, dict[str, tuple[str, ...]]]:
    lang = table.lang
    sets = table.table("sets", None)
    if sets is None:
        return {}
    parsed: dict[str, dict[str, tuple[str, ...]]] = {}
    for set_name in sets.raw:
        if not KEY_RE.fullmatch(set_name):
            raise ConfigError(
                message(lang, "cfg-clone-set-name", name=sets.name, value=repr(set_name))
            )
        condition = sets.table(set_name, None)
        assert condition is not None
        parsed[set_name] = {}
        for key in condition.raw:
            if not KEY_RE.fullmatch(key):
                raise ConfigError(
                    message(lang, "cfg-clone-set-key", name=condition.name, value=repr(key))
                )
            parsed[set_name][key] = condition.check_strings(condition.raw[key], condition.dotted(key))
    return parsed


TABLE = TableSpec("clone", ("roots", "urls", "sources"), _parse_clone)
