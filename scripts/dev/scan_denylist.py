# SPDX-License-Identifier: Apache-2.0
"""Fail when a tracked file contains a name from the denylist (design section 1).

The list is read from the environment variable MGTK_REPO_UTILS_DENYLIST: one
name per line, compared case-insensitively as a substring; `#` starts a comment
line. It is never a tracked file, since the list itself names what must not be
published. CI supplies it as a secret; a maintainer runs the same script with
the variable set locally.

Exit 0 when nothing matches, 1 on a match (each printed as `<path>:<line>`),
2 when the variable is unset or empty.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    raw = os.environ.get("MGTK_REPO_UTILS_DENYLIST", "")
    # One substring per line; `#` starts a comment line; blank lines are ignored.
    names = [
        line.strip().lower()
        for line in raw.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not names:
        print("scan_denylist: MGTK_REPO_UTILS_DENYLIST is unset or empty", file=sys.stderr)
        return 2
    listed = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
    found = 0
    for path in (p.decode() for p in listed.stdout.split(b"\0") if p):
        try:
            text = open(path, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            if any(name in lowered for name in names):
                print(f"{path}:{number}")
                found += 1
    if found:
        print(f"scan_denylist: {found} line(s) match the denylist", file=sys.stderr)
        return 1
    print("scan_denylist: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
