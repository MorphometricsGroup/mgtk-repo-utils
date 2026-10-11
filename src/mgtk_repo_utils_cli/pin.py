# SPDX-License-Identifier: Apache-2.0
"""pin: the consumer's hook configuration pins this tool by commit (design section 10).

Reads `prek.toml`, `.pre-commit-config.yaml` or `.pre-commit-config.yml` at the
root — the first that exists, in prek's order — and looks at every `repos`
entry that lists a hook whose id begins with `mgtk-repo-utils-`. The ids are the
contract, so the entry is found whatever URL or mirror its `repo:` line names.
It never compares the pin with the release that is running (section 2).
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

from mgtk_repo_utils.config import add_common_options, load, resolve_config_path, resolve_root
from mgtk_repo_utils.report import Report, ToolError, message, register

TOOL = "pin"
PROG = "mgtk-repo-utils"
HOOK_PREFIX = "mgtk-repo-utils-"
CONFIG_FILES = ("prek.toml", ".pre-commit-config.yaml", ".pre-commit-config.yml")
COMMIT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
FROZEN_RE = re.compile(r"#\s*frozen:\s*\S+")

MESSAGES: dict[str, tuple[str, str]] = {
    "summary-pin": (
        "{entries} entr{plural} of {file} pin this tool",
        "{file} の {entries} 件の項目がこの道具を固定",
    ),
    "pin-no-config": (
        "no hook configuration ({names}); the repository declares no release of this tool. "
        "Add one that names the hook repository with a `rev` that is a full commit",
        "hook の設定ファイル（{names}）がなく，このリポジトリはこの道具のリリースを宣言していない．"
        "hook リポジトリを full commit の `rev` で名指す設定を足す",
    ),
    "pin-missing": (
        "no entry lists a hook of this tool (an id beginning with `{prefix}`); add the hook "
        "repository with a `rev` that is a full commit",
        "この道具の hook（`{prefix}` で始まる id）を挙げる項目がない．hook リポジトリを "
        "full commit の `rev` で足す",
    ),
    "pin-not-commit": (
        "`rev: {rev}` is not a full commit: a tag or a branch can move and needs the network to "
        "resolve. Run `prek update --freeze` (pre-commit: `autoupdate --freeze`)",
        "`rev: {rev}` は full commit でない．タグやブランチは動きうるうえ，解決にネットワークが要る．"
        "`prek update --freeze`（pre-commit は `autoupdate --freeze`）を実行する",
    ),
    "pin-several": (
        "the entries pin different commits ({commits}); pin one release",
        "項目ごとに異なるコミットを固定している（{commits}）．1 つのリリースに揃える",
    ),
    "pin-unfrozen": (
        "`rev` has no `# frozen: <tag>` comment, so the release is not readable from the file; "
        "`prek update --freeze` writes it",
        "`rev` に `# frozen: <tag>` のコメントがなく，ファイルからリリースが読み取れない．"
        "`prek update --freeze` が書く",
    ),
    "pin-unreadable": (
        "{path}: cannot read the hook configuration ({detail}); fix the file",
        "{path}: hook の設定を読めない（{detail}）．ファイルを直す",
    ),
    "pin-yaml-missing": (
        "PyYAML is required to read {path} but is not installed in this environment; "
        "reinstall mgtk-repo-utils (PyYAML is one of its dependencies)",
        "{path} を読むのに PyYAML が必要だが，この環境にはインストールされていない．"
        "mgtk-repo-utils を入れ直す（PyYAML は依存の一つ）",
    ),
}
register(MESSAGES)


def _read(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ToolError(message("en", "pin-unreadable", path=path.name, detail=exc)) from exc
    try:
        import yaml
    except ImportError as exc:
        raise ToolError(message("en", "pin-yaml-missing", path=path.name)) from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ToolError(message("en", "pin-unreadable", path=path.name, detail=exc)) from exc


def _entries(data: object) -> list[dict[str, object]]:
    repos = data.get("repos") if isinstance(data, dict) else None
    found: list[dict[str, object]] = []
    for entry in repos if isinstance(repos, list) else []:
        if not isinstance(entry, dict):
            continue
        hooks = entry.get("hooks")
        ids = [h.get("id") for h in hooks if isinstance(h, dict)] if isinstance(hooks, list) else []
        if any(isinstance(i, str) and i.startswith(HOOK_PREFIX) for i in ids):
            found.append(entry)
    return found


def _line_of(text: str, rev: str) -> int | None:
    for number, line in enumerate(text.splitlines(), 1):
        if "rev" in line and rev in line:
            return number
    return None


def run(root: Path, lang: str) -> tuple[list[str], int]:
    """Check the pin; returns the report lines and the exit code."""
    report = Report(TOOL, lang)
    path = next((root / name for name in CONFIG_FILES if (root / name).is_file()), None)
    if path is None:
        report.error("pin-no-config", CONFIG_FILES[1], names=", ".join(CONFIG_FILES))
        return report.lines(), report.exit_code
    text = path.read_text(encoding="utf-8")
    entries = _entries(_read(path))
    if not entries:
        report.error("pin-missing", path.name, prefix=HOOK_PREFIX)
    commits: set[str] = set()
    for entry in entries:
        rev = entry.get("rev")
        if not isinstance(rev, str) or not COMMIT_RE.fullmatch(rev):
            report.error("pin-not-commit", path.name, _line_of(text, str(rev)), rev=repr(rev))
            continue
        commits.add(rev)
        line = _line_of(text, rev)
        if line is None or not FROZEN_RE.search(text.splitlines()[line - 1]):
            report.warn("pin-unfrozen", path.name, line)
    if len(commits) > 1:
        report.error("pin-several", path.name, commits=", ".join(sorted(c[:12] for c in commits)))
    plural = "y" if len(entries) == 1 else "ies"
    summary = message(lang, "summary-pin", entries=len(entries), plural=plural, file=path.name)
    return report.lines(summary), report.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"{PROG} pin",
        description="Check that the hook configuration pins this tool by a full commit "
        "(prek.toml, .pre-commit-config.yaml or .pre-commit-config.yml at the root).",
    )
    add_common_options(parser)
    return parser


def main(argv: list[str], cwd: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = cwd or Path.cwd()
    try:
        root = resolve_root(args.root, cwd)
        config = load(resolve_config_path(args.config, root, cwd), root)
        lines, code = run(root, config.lang)
    except ToolError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return code
