# SPDX-License-Identifier: Apache-2.0
"""`mgtk-repo-utils.toml` loading and validation (design section 4).

The core knows the top-level keys (`schema`, `requires`, `lang`). Every other
table is declared by a tool (`tool.TableSpec`) and parsed by it, so a table of
a tool that is not installed is an unknown table.
"""

from __future__ import annotations

import argparse
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .files import work_tree_top
from .report import LANGS, ToolError, message
from .tool import TableSpec, discover, tables_of

SCHEMA = 1
SEVERITIES = ("warn", "error")
READ_MODES = ("tracked", "worktree")
CONFIG_FILE = "mgtk-repo-utils.toml"
VERSION_RE = re.compile(r"\d+(\.\d+){0,2}")


class ConfigError(ToolError):
    """The configuration file is missing, unreadable or invalid."""


@dataclass(frozen=True)
class Config:
    path: Path
    root: Path
    lang: str
    requires: str | None = None
    # table name -> the typed configuration the table's tool parsed; absent = disabled
    tables: Mapping[str, object] = field(default_factory=dict)

    def table(self, name: str) -> object | None:
        """The parsed table `name`, or None when the file does not have it."""
        return self.tables.get(name)


def _version_tuple(text: str) -> tuple[int, int, int]:
    """Numeric leading components; `0.1.0.dev0` reads as (0, 1, 0)."""
    numbers: list[int] = []
    for piece in text.split("."):
        if not piece.isdigit():
            break
        numbers.append(int(piece))
    numbers += [0] * (3 - len(numbers))
    return (numbers[0], numbers[1], numbers[2])


class Table:
    """A TOML table with typed getters; unknown keys are rejected on creation."""

    def __init__(self, raw: object, name: str, lang: str, allowed: tuple[str, ...] | None):
        self.name = name
        self.lang = lang
        if not isinstance(raw, dict):
            raise self._type_error(name, "table")
        self.raw: dict[str, object] = raw
        if allowed is not None:
            for key, value in raw.items():
                if key not in allowed:
                    msg_id = "cfg-unknown-table" if isinstance(value, dict) else "cfg-unknown-key"
                    raise ConfigError(
                        message(lang, msg_id, name=self.dotted(key), version=__version__)
                    )

    def dotted(self, key: str) -> str:
        return f"{self.name}.{key}" if self.name else key

    def _type_error(self, name: str, kind: str) -> ConfigError:
        expected = message(self.lang, f"type-{kind}")
        return ConfigError(message(self.lang, "cfg-type", name=name, expected=expected))

    def has(self, key: str) -> bool:
        return key in self.raw

    def table(self, key: str, allowed: tuple[str, ...] | None) -> Table | None:
        if key not in self.raw:
            return None
        return Table(self.raw[key], self.dotted(key), self.lang, allowed)

    def string(self, key: str, default: str) -> str:
        value = self.raw.get(key, default)
        if not isinstance(value, str):
            raise self._type_error(self.dotted(key), "string")
        return value

    def boolean(self, key: str, default: bool) -> bool:
        value = self.raw.get(key, default)
        if not isinstance(value, bool):
            raise self._type_error(self.dotted(key), "boolean")
        return value

    def strings(self, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        value = self.raw.get(key, list(default))
        return self.check_strings(value, self.dotted(key))

    def check_strings(self, value: object, name: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise self._type_error(name, "strings")
        return tuple(value)

    def enum(self, key: str, default: str, choices: tuple[str, ...]) -> str:
        value = self.string(key, default)
        self.check_choice(value, self.dotted(key), choices)
        return value

    def check_choice(self, value: str, name: str, choices: tuple[str, ...]) -> None:
        if value not in choices:
            raise ConfigError(
                message(
                    self.lang,
                    "cfg-enum",
                    name=name,
                    choices=", ".join(f'"{c}"' for c in choices),
                    value=repr(value),
                )
            )

    def regex(self, key: str, default: str, flags: int = 0) -> tuple[str, re.Pattern[str]]:
        pattern = self.string(key, default)
        return pattern, self.compile(pattern, self.dotted(key), flags)

    def compile(self, pattern: str, name: str, flags: int = 0) -> re.Pattern[str]:
        try:
            return re.compile(pattern, flags)
        except re.error as exc:
            raise ConfigError(message(self.lang, "cfg-regex", name=name, detail=exc)) from exc


def load(path: Path, root: Path, tables: Mapping[str, TableSpec] | None = None) -> Config:
    """Read and validate the configuration file at `path`.

    `tables` are the tables the installed tools declare (`tool.tables_of`);
    None discovers them from the installed distributions.
    """
    if tables is None:
        tables = tables_of(discover())
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(message("en", "cfg-missing", path=path)) from exc
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(message("en", "cfg-parse", path=path, detail=exc)) from exc

    declared_lang = data.get("lang")
    message_lang = declared_lang if declared_lang in LANGS else "en"
    if "schema" not in data:
        raise ConfigError(message(message_lang, "cfg-schema-missing", path=path))
    schema = data["schema"]
    if isinstance(schema, bool) or not isinstance(schema, int):
        raise ConfigError(
            message(message_lang, "cfg-type", name="schema", expected=message(message_lang, "type-integer"))
        )
    if schema != SCHEMA:
        raise ConfigError(
            message(
                message_lang, "cfg-schema-unsupported", path=path, value=schema, version=__version__
            )
        )
    requires = data.get("requires")
    if requires is not None:
        _check_requires(requires, path, message_lang)

    top = Table(data, "", message_lang, ("schema", "requires", "lang", *tables))
    lang = top.enum("lang", "en", LANGS)
    parsed: dict[str, object] = {}
    for name, spec in tables.items():
        table = top.table(name, spec.keys)
        if table is not None:
            parsed[name] = spec.parse(table, lang)
    return Config(path=path, root=root, lang=lang, requires=requires, tables=parsed)


def _check_requires(requires: object, path: Path, lang: str) -> None:
    if not isinstance(requires, str) or not VERSION_RE.fullmatch(requires):
        raise ConfigError(message(lang, "cfg-requires-invalid", value=repr(requires)))
    if _version_tuple(requires) > _version_tuple(__version__):
        raise ConfigError(
            message(
                lang, "cfg-requires-too-new", path=path, required=requires, version=__version__
            )
        )


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        metavar="PATH",
        help="repository root (default: top level of the git work tree of the current "
        "directory, else the current directory)",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=f"configuration file (default: <root>/{CONFIG_FILE})",
    )


def resolve_root(root_arg: str | None, cwd: Path) -> Path:
    if root_arg is not None:
        root = (cwd / root_arg).resolve()
    else:
        root = work_tree_top(cwd) or cwd.resolve()
    if not root.is_dir():
        raise ConfigError(message("en", "root-missing", path=root))
    return root


def resolve_config_path(config_arg: str | None, root: Path, cwd: Path) -> Path:
    if config_arg is None:
        return root / CONFIG_FILE
    return (cwd / config_arg).resolve()


def load_for_tool(args: argparse.Namespace, tool: str, cwd: Path) -> Config:
    """Resolve root and config path from the common options, load, and require the tool's table."""
    tools = discover()
    root = resolve_root(args.root, cwd)
    config = load(resolve_config_path(args.config, root, cwd), root, tables_of(tools))
    spec = tools[tool].table if tool in tools else None
    if spec is not None and config.table(spec.name) is None:
        raise ConfigError(
            message(config.lang, "tool-disabled", table=spec.name, path=config.path, tool=tool)
        )
    return config
