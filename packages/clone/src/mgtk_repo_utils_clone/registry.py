# SPDX-License-Identifier: Apache-2.0
"""Registry loading, entry resolution and the static check (design sections 13 and 15).

This is the only module that imports PyYAML, and it does so inside `load`, so a
repository without PyYAML keeps every other tool. Nothing here reads the
environment except `expand`, which `resolve <id>` and `clone` call for the one
entry they handle; the static check reads declarations only.
"""

from __future__ import annotations

import datetime
import functools
import os
import re
import shlex
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from mgtk_repo_utils.config import Config
from mgtk_repo_utils.patterns import glob_regex
from mgtk_repo_utils.report import ERROR, Problem, ToolError, message

from .config import CONTROL_RE, PLACEHOLDER_RE, VARIABLE_RE, CloneConfig, RoutedRoot, SourceConfig


def clone_config(config: Config) -> CloneConfig:
    cfg = config.table("clone")
    assert isinstance(cfg, CloneConfig)
    return cfg


@dataclass(frozen=True)
class Entry:
    """One entry a source yields, with everything the checks derived from it."""

    index: int  # position in Resolution.entries
    source: SourceConfig
    file: str
    position: str  # for example `teams[2].services[0]`
    id: str | None  # None when it cannot be determined
    aliases: tuple[str, ...]
    url: str | None
    dir: str | None  # None when absent or not a single path component
    deviation: str | None  # the declared `local` text, when it is a string
    root: str  # the source's root, or the deviation's longest-matching root
    excluded: bool
    destination: str | None  # declared text: the deviation, or `<root>/<dir>`
    sets: frozenset[str] = frozenset()  # the source's sets the entry belongs to

    @property
    def names(self) -> tuple[str, ...]:
        return ((self.id,) if self.id else ()) + self.aliases

    @property
    def label(self) -> str:
        """`<file>: <position> (<id>)`, or without the id when it is unknown."""
        return _label(self.file, self.position, self.id)


@dataclass(frozen=True)
class Resolution:
    entries: tuple[Entry, ...]
    problems: tuple[Problem, ...]  # every problem of design section 15
    sources: int
    _by_name: Mapping[str, Entry]
    _attached: Mapping[int, tuple[Problem, ...]]
    set_names: tuple[str, ...] = ()  # every set some source declares, in first-declared order

    def find(self, name: str) -> Entry | None:
        """The entry whose id or alias is `name`, excluded entries included."""
        return self._by_name.get(name)

    def declares_set(self, name: str) -> bool:
        """Whether any source declares the set `name`."""
        return name in self.set_names

    def set_entries(self, name: str) -> list[Entry]:
        """The entries of the set `name`: source order, then entry order."""
        return [entry for entry in self.entries if name in entry.sets]

    def problems_for(self, entry: Entry) -> list[Problem]:
        """The problems that attach to `entry` (design section 16, step 1)."""
        return list(self._attached.get(entry.index, ()))


def _label(file: str, position: str, ident: str | None) -> str:
    where = f"{file}: {position}"
    return f"{where} ({_show(ident)})" if ident else where


def _show(text: str | None) -> str:
    """Text safe to print on one line: whitespace and control characters are escaped."""
    return "".join(
        c if c.isprintable() else c.encode("unicode_escape").decode("ascii") for c in text or ""
    )


def _kind(lang: str, present: bool, value: object) -> str:
    if not present:
        return message(lang, "kind-absent")
    if value is None:
        return message(lang, "kind-null")
    if isinstance(value, str):
        return message(lang, "kind-string" if value else "kind-empty")
    if isinstance(value, dict):
        return message(lang, "kind-mapping")
    if isinstance(value, list):
        return message(lang, "kind-list")
    if isinstance(value, bool):
        return message(lang, "kind-boolean")
    if isinstance(value, int | float):
        return message(lang, "kind-number")
    if isinstance(value, datetime.date):
        return message(lang, "kind-date")
    return message(lang, "kind-other")


def basename(url: str) -> str:
    """The directory name `git clone` chooses (design section 13, `id`)."""
    text = url.rstrip("/")
    text = text.removesuffix("/.git")
    text = text[max(text.rfind("/"), text.rfind(":")) + 1 :]
    return text.removesuffix(".git")


def _unfit(text: str) -> bool:
    """Whitespace or a control character."""
    return bool(CONTROL_RE.search(text)) or any(c.isspace() for c in text)


def _dir_ok(name: str) -> bool:
    return (
        name not in ("", ".", "..")
        and not name.startswith("-")
        and "/" not in name
        and "\\" not in name
        and not CONTROL_RE.search(name)
    )


def _local_form_ok(text: str) -> bool:
    """`~/<path>`, `/<path>` or `$NAME/<path>`, with no empty, `.` or `..` component."""
    if CONTROL_RE.search(text):
        return False
    if text.startswith("~/"):
        rest = text[2:]
    elif text.startswith("/"):
        rest = text[1:]
    elif text.startswith("$"):
        name, separator, rest = text[1:].partition("/")
        if not separator or not VARIABLE_RE.fullmatch(name):
            return False
    else:
        return False
    return all(part not in ("", ".", "..") for part in rest.split("/"))


@functools.cache
def _url_pattern(pattern: str) -> re.Pattern[str]:
    return glob_regex(pattern)


# git reads `<transport>::<address>` as a remote helper whatever `clone.urls` admits.
HELPER_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*::")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _ancestors(text: str) -> list[str]:
    return [text[:i] for i, char in enumerate(text) if char == "/" and i > 0]


class _Problems:
    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.all: list[Problem] = []
        self.attached: dict[int, list[Problem]] = {}

    def add(self, path: str, msg_id: str, *entries: Entry, **params: object) -> None:
        problem = Problem(path, None, ERROR, msg_id, message(self.lang, msg_id, **params))
        self.all.append(problem)
        for entry in entries:
            self.attached.setdefault(entry.index, []).append(problem)


def _config_name(config: Config) -> str:
    try:
        return config.path.relative_to(config.root).as_posix()
    except ValueError:
        return str(config.path)


def _read_registry(config: Config, source: SourceConfig, tool: str) -> object:
    try:
        import yaml
    except ImportError as exc:
        command = {"resolve": "resolve --check", "check": "check"}.get(tool, f"{tool} <id>")
        raise ToolError(message(config.lang, "resolve-yaml-missing", command=command)) from exc
    try:
        data = yaml.safe_load((config.root / source.file).read_bytes())
    except OSError as exc:
        raise ToolError(
            message(
                config.lang,
                "resolve-file-unreadable",
                path=source.file,
                detail=exc.strerror or exc,
                source=source.display,
            )
        ) from exc
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        detail = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        if mark is None:
            raise ToolError(
                message(config.lang, "resolve-yaml-error", path=source.file, detail=detail)
            ) from exc
        raise ToolError(
            message(
                config.lang,
                "resolve-yaml-line",
                path=source.file,
                line=mark.line + 1,
                detail=detail,
            )
        ) from exc
    except (ValueError, OverflowError, RecursionError) as exc:
        # PyYAML's constructors raise these for `2024-02-30`, a huge number or deep nesting.
        detail = (str(exc).splitlines() or [type(exc).__name__])[0]
        raise ToolError(
            message(config.lang, "resolve-yaml-error", path=source.file, detail=detail)
        ) from exc
    if not isinstance(data, dict):
        raise ToolError(message(config.lang, "resolve-top-level", path=source.file))
    return data


def _segments(entries: str) -> list[tuple[str, bool]]:
    return [
        (part.removesuffix("[]"), part.endswith("[]")) for part in entries.split(".")
    ]


def _walk(
    value: object,
    segments: list[tuple[str, bool]],
    position: str,
    found: list[tuple[str, dict]],
    errors: list[tuple[str, str, dict[str, object]]],
    lang: str,
    source: SourceConfig,
) -> None:
    """Collect the final mappings under `value` into `found`, and walk errors into `errors`."""
    if not segments:
        if isinstance(value, dict):
            found.append((position, value))
        elif value is not None:
            errors.append(
                (position, "walk-final", {"kind": _kind(lang, True, value), "source": source.display})
            )
        return
    key, is_list = segments[0]
    if not isinstance(value, dict):
        errors.append(
            (
                position,
                "walk-key",
                {"key": key, "kind": _kind(lang, True, value), "source": source.display},
            )
        )
        return
    child = value.get(key)
    child_position = f"{position}.{key}" if position else key
    if child is None:
        return
    if not is_list:
        _walk(child, segments[1:], child_position, found, errors, lang, source)
        return
    if not isinstance(child, list):
        errors.append(
            (
                child_position,
                "walk-list",
                {"key": key, "kind": _kind(lang, True, child), "source": source.display},
            )
        )
        return
    for index, item in enumerate(child):
        if item is not None:
            _walk(item, segments[1:], f"{child_position}[{index}]", found, errors, lang, source)


def _make_entry(
    index: int,
    source: SourceConfig,
    position: str,
    mapping: dict,
    clone: CloneConfig,
    lang: str,
) -> tuple[Entry, list[tuple[str, dict[str, object]]]]:
    """The entry for one mapping, and its problems of checks 2, 3, 5, 6 and 7 (none if excluded)."""
    pending: list[tuple[str, dict[str, object]]] = []

    def problem(msg_id: str, **params: object) -> None:
        pending.append((msg_id, params))

    reported: set[str] = set()

    def bad_value(key: str) -> None:
        if key in reported:
            return
        reported.add(key)
        problem("entry-value", key=key, kind=_kind(lang, key in mapping, mapping.get(key)))

    # URL
    values: dict[str, str] = {}
    placeholders = dict.fromkeys(PLACEHOLDER_RE.findall(source.url))
    for key in placeholders:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            values[key] = value
        else:
            bad_value(key)
    url = (
        PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], source.url)
        if len(values) == len(placeholders)
        else None
    )

    # id
    ident: str | None
    if source.id:
        value = mapping.get(source.id)
        if isinstance(value, str) and value:
            ident = value
        else:
            ident = None
            bad_value(source.id)
    else:
        ident = (basename(url) if url is not None else "") or None
        if ident is None and url is not None:
            problem("entry-no-id")

    # aliases
    aliases: tuple[str, ...] = ()
    if source.aliases:
        value = mapping.get(source.aliases)
        if isinstance(value, list):
            aliases = tuple(item for item in value if isinstance(item, str) and item)
            if len(aliases) != len(value):
                problem("entry-aliases", key=source.aliases, kind=_kind(lang, True, value))
        elif value is not None:
            problem("entry-aliases", key=source.aliases, kind=_kind(lang, True, value))

    excluded = ident is not None and any(
        name in source.exclude for name in ((ident,) + aliases)
    )

    # root: a name, or the one the entry's value selects through `map` (check 10)
    selected: object = None
    chosen: str | None = None
    if isinstance(source.root, RoutedRoot):
        selected = _with_default(mapping, source.root.by, source)
        if isinstance(selected, str):
            chosen = source.root.map.get(selected)
    else:
        chosen = source.root

    def built(**fields: object) -> Entry:
        defaults: dict[str, object] = {
            "index": index,
            "source": source,
            "file": source.file,
            "position": position,
            "id": ident,
            "aliases": aliases,
            "url": url,
            "dir": None,
            "deviation": None,
            "root": chosen or "",
            "excluded": excluded,
            "destination": None,
        }
        return Entry(**(defaults | fields))  # type: ignore[arg-type]

    if excluded:
        return built(), []

    for kind, text in (
        [("name-id", ident)]
        + [("name-alias", alias) for alias in aliases]
        + [("name-url", url)]
    ):
        if text is None:
            continue
        if _unfit(text):
            problem("entry-chars", kind=message(lang, kind), value=_show(text))
        if kind != "name-url" and text.startswith("-"):
            problem("entry-dash", kind=message(lang, kind), value=_show(text))

    if chosen is None:
        assert isinstance(source.root, RoutedRoot)
        if isinstance(selected, str):
            problem("entry-route-unmapped", key=source.root.by, value=_show(selected))
        else:
            by = source.root.by
            problem("entry-route", key=by, kind=_kind(lang, by in mapping, mapping.get(by)))

    # directory
    dir_name = ident if source.dir == "id" else (basename(url) if url is not None else None)
    if dir_name is not None and not _dir_ok(dir_name):
        problem("entry-dir", value=_show(dir_name))
        dir_name = None

    if url is not None:
        if HELPER_RE.match(url):
            problem("url-helper", value=_show(url))
        elif not any(_url_pattern(p).fullmatch(url) for p in clone.urls):
            problem("url-unmatched", value=_show(url))

    # declared deviation
    roots = clone.roots
    default = f"{roots[chosen]}/{dir_name}" if dir_name is not None and chosen else None
    deviation: str | None = None
    root_name = chosen or ""
    destination = default
    raw = mapping.get(source.local) if source.local else None
    if raw is not None:
        destination = None
        if not isinstance(raw, str):
            problem("local-type", key=source.local, kind=_kind(lang, True, raw))
        else:
            deviation = raw
            matching = [name for name, text in roots.items() if raw.startswith(text + "/")]
            if not _local_form_ok(raw):
                problem("local-form", value=_show(raw))
            elif not matching:
                problem("local-outside", value=_show(raw))
            else:
                root_name = max(matching, key=lambda name: len(roots[name]))
                destination = raw
                if raw == default:
                    problem("local-default", value=_show(raw), key=source.local)

    entry = built(
        dir=dir_name,
        deviation=deviation,
        root=root_name,
        destination=destination if chosen else None,
        sets=_memberships(mapping, source),
    )
    return entry, pending


def _with_default(mapping: dict, key: str, source: SourceConfig) -> object:
    """The entry's value of `key`, or the source's default where it is absent or null."""
    value = mapping.get(key)
    return source.defaults.get(key) if value is None else value


def _memberships(mapping: dict, source: SourceConfig) -> frozenset[str]:
    """The sets whose condition the entry meets: a listed key's value, a string, is among the values."""
    member = set()
    for name, condition in source.sets.items():
        for key, values in condition.items():
            value = _with_default(mapping, key, source)
            if not (isinstance(value, str) and value in values):
                break
        else:
            member.add(name)
    return frozenset(member)


def load(config: Config, tool: str = "resolve") -> Resolution:
    """Read every registry, derive the entries and run all checks of design section 15.

    `tool` names the tool being run, for the remedy when PyYAML is missing.
    """
    clone = clone_config(config)
    lang = config.lang
    config_name = _config_name(config)
    problems = _Problems(lang)
    documents: dict[str, object] = {}
    entries: list[Entry] = []
    by_source: dict[str, list[Entry]] = {}

    for source in clone.sources:
        if source.file not in documents:
            documents[source.file] = _read_registry(config, source, tool)
        found: list[tuple[str, dict]] = []
        errors: list[tuple[str, str, dict[str, object]]] = []
        _walk(documents[source.file], _segments(source.entries), "", found, errors, lang, source)
        for position, msg_id, params in errors:
            problems.add(f"{source.file}: {position}", msg_id, **params)
        yielded = by_source.setdefault(source.name, [])
        if not found and not errors:
            problems.add(
                f"{config_name}: {source.display}",
                "source-empty",
                file=source.file,
                entries=source.entries,
            )
        for position, mapping in found:
            entry, pending = _make_entry(len(entries), source, position, mapping, clone, lang)
            entries.append(entry)
            yielded.append(entry)
            for msg_id, params in pending:
                problems.add(entry.label, msg_id, entry, **params)

    _check_ids(entries, problems)
    _check_destinations(entries, clone, problems)
    for source in clone.sources:
        known = {name for entry in by_source[source.name] for name in entry.names}
        for value in dict.fromkeys(source.exclude):
            if value not in known:
                problems.add(
                    f"{config_name}: {source.display}", "exclude-unmatched", value=_show(value)
                )

    by_name: dict[str, Entry] = {}
    for entry in entries:
        for name in entry.names:
            by_name.setdefault(name, entry)
    return Resolution(
        entries=tuple(entries),
        problems=tuple(problems.all),
        sources=len(clone.sources),
        _by_name=by_name,
        _attached={index: tuple(found) for index, found in problems.attached.items()},
        set_names=tuple(dict.fromkeys(name for source in clone.sources for name in source.sets)),
    )


ROUTE_POSITION = "--route"


def route(
    config: Config, resolution: Resolution, source_name: str, fields: list[str]
) -> tuple[Entry, list[Problem]]:
    """The entry `--route` describes, and the problems that attach to it (design section 14).

    The entry is built as the source would build one the registry holds, then checked as if
    it were added after the registry's own entries: checks 2, 3, 5, 6, 7 and 10 on it, and
    4 and 8 against the entries already there. The registry's own problems are not reported.
    """
    clone = clone_config(config)
    lang = config.lang
    source = next((s for s in clone.sources if s.declared and s.declared == source_name), None)
    if source is None:
        raise ToolError(
            message(
                lang,
                "route-source-unknown",
                name=_show(source_name),
                known=list_names([s.declared for s in clone.sources if s.declared], lang),
            )
        )
    mapping: dict[str, str] = {}
    for field in fields:
        key, equals, value = field.partition("=")
        if not (key and equals):
            raise ToolError(message(lang, "route-field", field=_show(field)))
        mapping[key] = value
    entry, pending = _make_entry(
        len(resolution.entries), source, ROUTE_POSITION, mapping, clone, lang
    )
    if entry.excluded:
        raise ToolError(
            message(lang, "resolve-excluded", id=_show(entry.id), source=source.display)
        )
    problems = _Problems(lang)
    for msg_id, params in pending:
        problems.add(entry.label, msg_id, entry, **params)
    entries = [*resolution.entries, entry]
    _check_ids(entries, problems)
    _check_destinations(entries, clone, problems)
    return entry, problems.attached.get(entry.index, [])


def list_names(names: list[str], lang: str) -> str:
    """The names as a list for a message, or "none" when there are none."""
    return ", ".join(f"`{_show(name)}`" for name in names) or message(lang, "none-declared")


def _check_ids(entries: list[Entry], problems: _Problems) -> None:
    """Check 4: ids unique across all sources, excluded entries included."""
    owners: dict[str, list[Entry]] = {}
    for entry in entries:
        seen = {entry.id} if entry.id else set()
        reported: set[str] = set()
        for alias in entry.aliases:
            if alias in seen and alias not in reported:
                reported.add(alias)
                msg_id = "alias-is-id" if alias == entry.id else "alias-repeated"
                problems.add(entry.label, msg_id, entry, value=_show(alias))
            seen.add(alias)
        for name in dict.fromkeys(entry.names):
            owners.setdefault(name, []).append(entry)
    for name, sharing in owners.items():
        for later_index, later in enumerate(sharing):
            for earlier in sharing[:later_index]:
                problems.add(
                    later.label,
                    "id-collision",
                    earlier,
                    later,
                    value=_show(name),
                    other=f"{earlier.file}: {earlier.position}",
                )


def _check_destinations(entries: list[Entry], clone: CloneConfig, problems: _Problems) -> None:
    """Check 8: destinations that overlap each other, or equal or contain a root."""
    by_destination: dict[str, list[Entry]] = {}
    for entry in entries:
        if not entry.excluded and entry.destination is not None:
            by_destination.setdefault(_fold(entry.destination), []).append(entry)

    def overlap(first: Entry, second: Entry) -> None:
        later, earlier = (second, first) if second.index > first.index else (first, second)
        problems.add(
            later.label,
            "dest-overlap",
            earlier,
            later,
            dest=_show(later.destination),
            other=f"{earlier.file}: {earlier.position}",
            other_dest=_show(earlier.destination),
        )

    for folded, sharing in by_destination.items():
        for later_index, later in enumerate(sharing):
            for earlier in sharing[:later_index]:
                overlap(earlier, later)
        for ancestor in _ancestors(folded):
            for outer in by_destination.get(ancestor, ()):
                for inner in sharing:
                    overlap(outer, inner)

    for name, text in clone.roots.items():
        folded = _fold(text)
        for candidate in [folded, *_ancestors(folded)]:
            for entry in by_destination.get(candidate, ()):
                problems.add(
                    entry.label,
                    "dest-root",
                    entry,
                    dest=_show(entry.destination),
                    root=name,
                    root_text=text,
                )


def expand(text: str, root: str, env: Mapping[str, str] | None, lang: str) -> str:
    """Expand `~` and `$NAME` at the start of a declared root or deviation (design section 14)."""
    env = os.environ if env is None else env
    if text.startswith("~/"):
        name, rest = "HOME", text[1:]
    elif text.startswith("$"):
        variable, separator, tail = text[1:].partition("/")
        name, rest = variable, separator + tail
    else:
        return text
    value = env.get(name)
    if not value:
        raise ToolError(message(lang, "expand-unset", variable=name, root=root, text=text))
    if not value.startswith("/") or CONTROL_RE.search(value):
        raise ToolError(
            message(lang, "expand-bad", variable=name, value=_show(value), root=root, text=text)
        )
    return value.rstrip("/") + rest if rest else value


def expand_destination(
    entry: Entry, roots: Mapping[str, str], env: Mapping[str, str] | None = None, lang: str = "en"
) -> str:
    """The entry's destination with the root expanded; only this entry's root is looked up."""
    if entry.deviation is not None:
        return expand(entry.deviation, entry.root, env, lang)
    assert entry.dir is not None
    return expand(roots[entry.root], entry.root, env, lang).rstrip("/") + "/" + entry.dir
