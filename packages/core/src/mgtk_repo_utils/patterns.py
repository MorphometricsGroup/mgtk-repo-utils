# SPDX-License-Identifier: Apache-2.0
"""Glob matching shared by link-check (`[links].exclude`) and the clone tools (`[clone].urls`)."""

from __future__ import annotations

import re


def glob_regex(pattern: str) -> re.Pattern[str]:
    """A glob over `/`-separated text: `*` and `?` stay within one segment, `**` spans them."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
            continue
        char = pattern[i]
        out.append("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char))
        i += 1
    return re.compile("".join(out))
