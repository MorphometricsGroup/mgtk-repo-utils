# SPDX-License-Identifier: Apache-2.0
"""Helpers shared by the tests. Nothing here touches a repository outside tmp_path."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGES = REPO / "packages"
CONFIG_FILE = "mgtk-repo-utils.toml"
PROG = "mgtk-repo-utils"
# The command as the tests run it: the installed CLI module of this environment.
COMMAND = [sys.executable, "-m", "mgtk_repo_utils_cli"]


def toml_value(value: object) -> str:
    """A TOML value for a string, boolean, list or (inline) table; JSON covers all but tables."""
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)} = {toml_value(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return json.dumps(value)


def clean_env() -> dict[str, str]:
    """The environment without GIT_* variables a hook may have set."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=clean_env()
    )
    return proc.stdout


@dataclass
class Result:
    code: int
    out: str
    err: str


def run_command(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> Result:
    """Run `mgtk-repo-utils <args>` in a subprocess."""
    proc = subprocess.run(
        [*COMMAND, *args], cwd=cwd, capture_output=True, text=True, env=env or clean_env()
    )
    return Result(proc.returncode, proc.stdout, proc.stderr)


class Repo:
    """A temporary directory, optionally a git work tree, with helpers to fill and run it."""

    def __init__(self, root: Path, init: bool = True) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        if init:
            git(root, "init", "-q")

    def write(self, rel: str, text: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def read(self, rel: str) -> str:
        return (self.root / rel).read_bytes().decode("utf-8")

    def stage(self, *paths: str) -> None:
        git(self.root, "add", "-f", *(paths or ("-A",)))

    def run(
        self,
        *args: str,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
        drop_env: tuple[str, ...] = (),
    ) -> Result:
        """Run a tool in this repository.

        `drop_env` names variables to remove from the child's environment.
        """
        env = {k: v for k, v in (clean_env() | (extra_env or {})).items() if k not in drop_env}
        return run_command(*args, cwd=cwd or self.root, env=env)


def issue_text(
    status: str = "open",
    *,
    title: str | None = "A title",
    created: str | None = "2026-01-01",
    **extra: str,
) -> str:
    lines = ["---"]
    if title is not None:
        lines.append(f"title: {title}")
    lines.append(f"status: {status}")
    if created is not None:
        lines.append(f"created: {created}")
    lines.extend(f"{key}: {value}" for key, value in extra.items())
    lines += ["---", "", "Body.", ""]
    return "\n".join(lines)


def with_id(stem: str, text: str) -> str:
    """Insert `id: <stem>` after the opening delimiter."""
    return text.replace("---\n", f"---\nid: {stem}\n", 1)


MARKERS = "<!-- BEGIN GENERATED: issues-active -->\n<!-- END GENERATED: issues-active -->\n"
README = "# Issues\n\n" + MARKERS

BASIC_CONFIG = """\
schema = 1
lang = "en"

[issues]

[issues.fields]
priority = ["high", "low"]

[issues.views."README.md"]
marker = "issues-active"
columns = ["issue", "title", "priority", "created"]
sort = ["priority", "created"]
"""


COMMIT = "0123456789abcdef0123456789abcdef01234567"
# A hook configuration that pins this tool by a frozen commit (design section 10).
PIN_CONFIG = f"""\
repos:
  - repo: git@example.com:example/mgtk-repo-utils.git
    rev: {COMMIT}  # frozen: v0.1.0
    hooks:
      - id: mgtk-repo-utils-check
"""


def pinned(repo: Repo) -> Repo:
    repo.write(".pre-commit-config.yaml", PIN_CONFIG)
    return repo


def add_issue(repo: Repo, stem: str, status: str = "open", **kwargs: object) -> None:
    extra = {k: str(v) for k, v in kwargs.items() if k not in ("title", "created")}
    text = issue_text(
        status,
        title=kwargs.get("title", f"Title of {stem}"),  # type: ignore[arg-type]
        created=kwargs.get("created", "2026-01-01"),  # type: ignore[arg-type]
        **extra,
    )
    repo.write(f"issues/items/{stem}.md", with_id(stem, text))


def basic_repo(tmp_path: Path, config: str = BASIC_CONFIG, readme: str = README) -> Repo:
    repo = Repo(tmp_path / "repo")
    repo.write(CONFIG_FILE, config)
    repo.write("issues/README.md", readme)
    return repo
