# SPDX-License-Identifier: Apache-2.0
"""Development only; never shipped in a distribution and not run in CI.

Regenerates tests/fixtures/slug-headings-synthetic.expected.json: the slug that
github-slugger itself gives each heading of tests/fixtures/slug-headings-synthetic.md.
Expected values come from the upstream oracle (slug-oracle.mjs, run under node with one
Slugger for the whole file, so repeats get -1), never from repo-kit's own port.

The oracle's input is the heading text. In this fixture the only inline markup is
code-span backticks, so the text is the line without its `#` marker and backticks; that
rule is written here, apart from the port under test.

usage: gen-slug-expected.py <github-slugger directory holding slug-oracle.mjs>
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    upstream = Path(argv[0]).resolve()
    source = FIXTURES / "slug-headings-synthetic.md"
    headings = [
        line for line in source.read_text(encoding="utf-8").split("\n") if line.startswith("#")
    ]
    texts = [re.sub(r"^#+ ", "", line).replace("`", "") for line in headings]
    proc = subprocess.run(
        ["node", str(upstream / "slug-oracle.mjs")],
        input="\n".join(texts) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    answers = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [a["heading"] for a in answers] == texts
    entries = [
        {"heading": line, "text": text, "slug": answer["slug"]}
        for line, text, answer in zip(headings, texts, answers, strict=True)
    ]
    target = FIXTURES / "slug-headings-synthetic.expected.json"
    target.write_text(json.dumps(entries, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"{len(entries)} headings -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
