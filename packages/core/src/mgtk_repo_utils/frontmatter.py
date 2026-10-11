# SPDX-License-Identifier: Apache-2.0
"""Strict frontmatter reader (design section 6).

The reader accepts a strict subset of YAML, normalises values by the shape of
the key, and rejects everything else with a line number and a rule id. Only the
keys named in `shapes` are read; every other key is skipped together with the
lines indented under it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import NamedTuple

SCALAR = "scalar"
DATE = "date"
DATE_OR_NULL = "date-or-null"
LIST = "list"
ANY = "any"  # scalar or list, as written

ERROR = "error"
WARNING = "warning"

# Every rejection rule. The message catalogue holds `fm-<rule>` for each.
RULES = (
    "missing",
    "unterminated",
    "plain-hash",
    "plain-colon",
    "plain-indicator",
    "anchor",
    "alias",
    "tag",
    "quote-trailing",
    "tab-indent",
    "tab-before-comment",
    "duplicate-key",
    "nested-flow",
    "flow-mapping",
    "list-item-not-indented",
    "bad-date",
    "list-expected",
    "scalar-expected",
    "unterminated-quote",
    "bad-escape",
    "flow-unterminated",
    "flow-trailing",
    "flow-empty-item",
    "block-scalar-indicator",
    "syntax",
)

Value = str | date | list[str] | None

_KEY_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(?:([ \t]+)(.*))?$")
_LIST_ITEM = re.compile(r" *-(?:[ \t]+(.*))?$")
_BLOCK_HEADER = re.compile(r"([|>])(-?)(?:([ \t]+)(#.*)?)?$")
_HASH = re.compile(r"(?:^|[ \t])#")
_COLON = re.compile(r":(?:[ \t]|$)")
_TAB_INDENT = re.compile(r" *\t")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NULLS = frozenset({"null", "Null", "NULL", "~"})
_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}
_START_RULES = {"{": "flow-mapping", "&": "anchor", "*": "alias", "!": "tag"}


@dataclass(frozen=True)
class FmProblem:
    line: int
    rule: str
    severity: str
    key: str = ""


@dataclass
class Frontmatter:
    present: bool = False
    values: dict[str, Value] = field(default_factory=dict)
    problems: list[FmProblem] = field(default_factory=list)
    rejected: set[str] = field(default_factory=set)  # read keys whose value was rejected
    body: list[str] = field(default_factory=list)  # lines after the closing `---`
    body_line: int = 1  # file line number of body[0]


class _Scan(NamedTuple):
    value: str | None
    tail: str
    index: int
    error: str | None


_BAD = ("bad", None)
_Read = tuple[str, "Value"]  # (kind, value) with kind "scalar" | "list" | "bad"
_Line = tuple[int, str]


def parse(text: str, shapes: Mapping[str, str]) -> Frontmatter:
    """Read the frontmatter of `text`; `shapes` maps each key to read to its shape."""
    result = Frontmatter()
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != "---":
        result.problems.append(FmProblem(1, "missing", ERROR))
        return result
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if end is None:
        result.problems.append(FmProblem(1, "unterminated", ERROR))
        return result
    result.present = True
    result.body = lines[end + 1 :]
    result.body_line = end + 2
    _Reader(lines, end, shapes, result).run()
    return result


def _indent(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _is_blank_or_comment(text: str) -> bool:
    stripped = text.strip()
    return not stripped or stripped.startswith("#")


def _trim_trailing(lines: list[_Line]) -> list[_Line]:
    end = len(lines)
    while end and _is_blank_or_comment(lines[end - 1][1]):
        end -= 1
    return lines[:end]


def _fold(texts: list[str]) -> str:
    """Fold stripped lines as YAML does: one break is a space, n blank lines are n breaks."""
    out = texts[0]
    blanks = 0
    for text in texts[1:]:
        if not text:
            blanks += 1
            continue
        out += ("\n" * blanks if blanks else " ") + text
        blanks = 0
    return out


def _fold_block(lines: list[str]) -> str:
    """Fold the content of a `>` block scalar; more-indented lines keep their breaks."""
    out: list[str] = []
    blanks = 0
    previous_more = False
    first = True
    for line in lines:
        if line == "":
            blanks += 1
            continue
        more = line[0] in " \t"
        if first:
            out.append("\n" * blanks)
        elif previous_more or more:
            out.append("\n" * (blanks + 1))
        else:
            out.append(" " if blanks == 0 else "\n" * blanks)
        out.append(line)
        previous_more = more
        blanks = 0
        first = False
    return "".join(out)


def _scan_quoted(segments: list[str], quote: str) -> _Scan:
    """Scan a quoted scalar. `segments[0]` follows the opening quote; later ones are
    continuation lines with leading whitespace removed."""
    out: list[str] = []
    blanks = 0
    for index, segment in enumerate(segments):
        if index > 0:
            if not segment.strip():
                blanks += 1
                continue
            out.append("\n" * blanks if blanks else " ")
            blanks = 0
        line: list[tuple[str, bool]] = []  # (char, literal)
        pos = 0
        while pos < len(segment):
            char = segment[pos]
            if quote == "'" and char == "'":
                if segment[pos + 1 : pos + 2] == "'":
                    line.append(("'", False))
                    pos += 2
                    continue
                out.extend(c for c, _ in line)
                return _Scan("".join(out), segment[pos + 1 :], index, None)
            if quote == '"' and char == '"':
                out.extend(c for c, _ in line)
                return _Scan("".join(out), segment[pos + 1 :], index, None)
            if quote == '"' and char == "\\":
                escaped = _ESCAPES.get(segment[pos + 1 : pos + 2])
                if escaped is None:
                    return _Scan(None, "", index, "bad-escape")
                line.append((escaped, False))
                pos += 2
                continue
            line.append((char, True))
            pos += 1
        while line and line[-1][1] and line[-1][0] in " \t":
            line.pop()
        out.extend(c for c, _ in line)
    return _Scan(None, "", len(segments) - 1, "unterminated-quote")


class _Reader:
    def __init__(
        self, lines: list[str], end: int, shapes: Mapping[str, str], result: Frontmatter
    ) -> None:
        self.lines = lines
        self.end = end  # index of the closing `---`
        self.shapes = shapes
        self.result = result

    def problem(self, rule: str, line: int, key: str = "", severity: str = ERROR) -> None:
        self.result.problems.append(FmProblem(line, rule, severity, key))

    def run(self) -> None:
        seen: set[str] = set()
        i = 1
        while i < self.end:
            text = self.lines[i]
            number = i + 1
            if not text.strip():
                i += 1
                continue
            if text.lstrip(" \t").startswith("#"):
                if _TAB_INDENT.match(text):
                    self.problem("tab-indent", number)
                i += 1
                continue
            if text[0] in " \t":
                self.problem("tab-indent" if _TAB_INDENT.match(text) else "syntax", number)
                i += 1
                continue
            match = _KEY_LINE.match(text)
            if match is None:
                rule = "list-item-not-indented" if text == "-" or text.startswith("- ") else "syntax"
                self.problem(rule, number)
                i += 1
                continue
            key = match.group(1)
            before = len(self.result.problems)
            owned, i = self._collect(i + 1, key)
            if key in seen:
                self.problem("duplicate-key", number, key)
                self.result.rejected.add(key)
                self.result.values.pop(key, None)
                continue
            seen.add(key)
            sep = match.group(2) or ""
            rest = (match.group(3) or "").rstrip()
            shape = self.shapes.get(key)
            if shape is None:
                self._skip_unknown(key, rest, owned, number)
                continue
            self._read_key(key, shape, sep, rest, owned, number)
            if any(p.severity == ERROR for p in self.result.problems[before:]):
                self.result.rejected.add(key)
                self.result.values.pop(key, None)

    def _collect(self, start: int, key: str) -> tuple[list[_Line], int]:
        """Lines owned by a key: the indented lines after it, with blanks and comments between."""
        owned: list[_Line] = []
        pending: list[_Line] = []
        i = start
        while i < self.end:
            text = self.lines[i]
            if not text.strip() or text.startswith("#"):
                pending.append((i + 1, text))
            elif text[0] in " \t":
                owned.extend(pending)
                pending = []
                owned.append((i + 1, text))
                if _TAB_INDENT.match(text):
                    self.problem("tab-indent", i + 1, key)
            else:
                break
            i += 1
        return owned, i - len(pending)

    def _skip_unknown(self, key: str, rest: str, owned: list[_Line], number: int) -> None:
        if not rest or rest[0] in "#[{\"'|>&*!%@`":
            return
        candidates = [(number, rest)] + [
            (n, t.strip()) for n, t in owned if not _is_blank_or_comment(t)
        ]
        # Other YAML readers fail or truncate on these, so each rule warns once per key.
        for rule, pattern in (("plain-hash", _HASH), ("plain-colon", _COLON)):
            for line, text in candidates:
                if pattern.search(text):
                    self.problem(rule, line, key, WARNING)
                    break

    def _read_key(
        self, key: str, shape: str, sep: str, rest: str, owned: list[_Line], number: int
    ) -> None:
        if rest and not rest.startswith("#"):
            kind, value = self._value(key, rest, owned, number)
            self._store(key, shape, kind, value, number)
            return
        if rest and "\t" in sep:
            self.problem("tab-before-comment", number, key)
        first = next((i for i, (_, t) in enumerate(owned) if not _is_blank_or_comment(t)), None)
        if first is None:
            self._store(key, shape, "scalar", None, number)
            return
        first_number, first_text = owned[first]
        stripped = first_text.strip()
        if stripped == "-" or stripped.startswith("- "):
            kind, value = self._block_list(key, owned[first:])
        else:
            kind, value = self._value(key, stripped, owned[first + 1 :], first_number)
        self._store(key, shape, kind, value, first_number)

    def _store(self, key: str, shape: str, kind: str, value: Value, number: int) -> None:
        if kind == "bad":
            return
        values = self.result.values
        if shape in (DATE, DATE_OR_NULL):
            if kind == "list":
                self.problem("scalar-expected", number, key)
            elif value is None:
                values[key] = None
            else:
                parsed = _parse_date(str(value))
                if parsed is None:
                    self.problem("bad-date", number, key)
                else:
                    values[key] = parsed
        elif shape == SCALAR:
            if kind == "list":
                self.problem("scalar-expected", number, key)
            else:
                values[key] = value
        elif shape == LIST:
            if kind == "list":
                values[key] = value
            elif value is None:
                values[key] = []
            else:
                self.problem("list-expected", number, key)
        else:
            values[key] = value

    def _value(self, key: str, first: str, cont: list[_Line], number: int) -> _Read:
        head = first[0]
        if head in "\"'":
            return self._quoted(key, first, cont, number)
        if head in "|>":
            return self._block_scalar(key, first, cont, number)
        if head == "[":
            return self._flow_list(key, first, cont, number)
        rule = _plain_start_rule(head)
        if rule is not None:
            self.problem(rule, number, key)
            return _BAD
        return self._plain(key, first, cont, number)

    def _plain(self, key: str, first: str, cont: list[_Line], number: int) -> _Read:
        pieces = [(number, first)] + [(n, t.strip()) for n, t in _trim_trailing(cont)]
        bad = False
        for line, text in pieces:
            if _HASH.search(text):
                self.problem("plain-hash", line, key)
                bad = True
            if _COLON.search(text):
                self.problem("plain-colon", line, key)
                bad = True
        if bad:
            return _BAD
        texts = [text for _, text in pieces]
        value = _fold(texts)
        return ("scalar", None if len(texts) == 1 and value in _NULLS else value)

    def _tail(self, tail: str, rule: str, key: str, number: int) -> bool:
        """Check what follows a closed value: spaces, then optionally a comment."""
        stripped = tail.strip()
        if not stripped:
            return True
        if tail[0] in " \t" and stripped.startswith("#"):
            if "\t" in tail[: len(tail) - len(tail.lstrip(" \t"))]:
                self.problem("tab-before-comment", number, key)
                return False
            return True
        self.problem(rule, number, key)
        return False

    def _quoted(self, key: str, first: str, cont: list[_Line], number: int) -> _Read:
        segments = [first[1:]] + [t.lstrip(" \t") for _, t in cont]
        scan = _scan_quoted(segments, first[0])
        if scan.error is not None:
            at_opening = scan.index == 0 or scan.error == "unterminated-quote"
            self.problem(scan.error, number if at_opening else cont[scan.index - 1][0], key)
            return _BAD
        for line, text in cont[scan.index :]:
            if not _is_blank_or_comment(text):
                self.problem("syntax", line, key)
                return _BAD
        close_line = number if scan.index == 0 else cont[scan.index - 1][0]
        if not self._tail(scan.tail, "quote-trailing", key, close_line):
            return _BAD
        return ("scalar", scan.value)

    def _block_scalar(self, key: str, header: str, cont: list[_Line], number: int) -> _Read:
        match = _BLOCK_HEADER.match(header)
        if match is None:
            self.problem("block-scalar-indicator", number, key)
            return _BAD
        if match.group(4) and "\t" in match.group(3):
            self.problem("tab-before-comment", number, key)
            return _BAD
        style, chomp = match.group(1), match.group(2)
        end = len(cont)
        while end and not cont[end - 1][1].strip():
            end -= 1
        body = cont[:end]
        if not body:
            return ("scalar", "")
        indent = _indent(next(t for _, t in body if t.strip()))
        lines: list[str] = []
        for line, text in body:
            if text.strip() and _indent(text) < indent:
                self.problem("syntax", line, key)
                return _BAD
            lines.append(text[indent:] if len(text) > indent else "")
        folded = "\n".join(lines) if style == "|" else _fold_block(lines)
        return ("scalar", folded if chomp == "-" else folded + "\n")

    def _flow_list(self, key: str, first: str, cont: list[_Line], number: int) -> _Read:
        rest = first[1:]
        items: list[str] = []
        while True:
            rest = rest.lstrip(" \t")
            if not rest:
                self.problem("flow-unterminated", number, key)
                return _BAD
            head = rest[0]
            if head == "]":
                rest = rest[1:]
                break
            if head == ",":
                self.problem("flow-empty-item", number, key)
                return _BAD
            if head in "[{":
                self.problem("nested-flow", number, key)
                return _BAD
            if head in "\"'":
                scan = _scan_quoted([rest[1:]], head)
                if scan.error is not None:
                    self.problem(
                        "flow-unterminated" if scan.error == "unterminated-quote" else scan.error,
                        number,
                        key,
                    )
                    return _BAD
                assert scan.value is not None
                items.append(scan.value)
                rest = scan.tail
            else:
                stop = min((p for p in (rest.find(","), rest.find("]")) if p >= 0), default=len(rest))
                chunk = rest[:stop].strip()
                rule = self._plain_item_rule(chunk)
                if rule is not None:
                    self.problem(rule, number, key)
                    return _BAD
                if chunk not in _NULLS:
                    items.append(chunk)
                rest = rest[stop:]
            rest = rest.lstrip(" \t")
            if rest.startswith(","):
                rest = rest[1:]
            elif rest.startswith("]"):
                rest = rest[1:]
                break
            else:
                self.problem("flow-unterminated" if not rest else "flow-trailing", number, key)
                return _BAD
        if not self._tail(rest, "flow-trailing", key, number):
            return _BAD
        for line, text in cont:
            if not _is_blank_or_comment(text):
                self.problem("syntax", line, key)
                return _BAD
        return ("list", items)

    @staticmethod
    def _plain_item_rule(chunk: str) -> str | None:
        if any(c in chunk for c in "[]{}"):
            return "nested-flow"
        rule = _plain_start_rule(chunk[0]) if chunk else None
        if rule is not None:
            return rule
        if _HASH.search(chunk):
            return "plain-hash"
        if _COLON.search(chunk):
            return "plain-colon"
        return None

    def _block_list(self, key: str, owned: list[_Line]) -> _Read:
        items: list[str] = []
        ok = True
        base: int | None = None
        i = 0
        while i < len(owned):
            number, text = owned[i]
            if _is_blank_or_comment(text):
                i += 1
                continue
            match = _LIST_ITEM.match(text)
            if base is None:
                base = _indent(text)
            if match is None or _indent(text) != base:
                self.problem("syntax", number, key)
                ok = False
                i += 1
                continue
            j = i + 1
            cont: list[_Line] = []
            while j < len(owned) and (not owned[j][1].strip() or _indent(owned[j][1]) > base):
                cont.append(owned[j])
                j += 1
            i = j
            head = (match.group(1) or "").strip()
            if not head or head.startswith("#"):
                if any(not _is_blank_or_comment(t) for _, t in cont):
                    self.problem("syntax", number, key)
                    ok = False
                continue
            kind, value = self._value(key, head, cont, number)
            if kind == "list":
                self.problem("nested-flow", number, key)
                ok = False
            elif kind == "bad":
                ok = False
            elif value is not None:
                items.append(str(value))
        return ("list", items) if ok else _BAD


def _plain_start_rule(head: str) -> str | None:
    if head in _START_RULES:
        return _START_RULES[head]
    return "plain-indicator" if head in "%@`" else None


def _parse_date(text: str) -> date | None:
    if not _DATE.fullmatch(text):
        return None
    try:
        return date(int(text[:4]), int(text[5:7]), int(text[8:10]))
    except ValueError:
        return None
