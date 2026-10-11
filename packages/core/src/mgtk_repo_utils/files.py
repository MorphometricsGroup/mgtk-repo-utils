# SPDX-License-Identifier: Apache-2.0
"""File listing: tracked | worktree | filesystem (design section 5).

Every path returned is relative to the root, uses `/`, and is sorted. Git is
always asked with `-z`, so no path is ever quoted.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .report import ToolError


class GitError(ToolError):
    """A git command failed inside a work tree."""


@dataclass
class Listing:
    files: list[str]
    source: str  # "tracked" | "worktree" | "filesystem"
    missing: list[str] = field(default_factory=list)  # tracked paths absent from the working tree


def _git_env() -> dict[str, str] | None:
    """The environment for git calls that move with `-C`.

    A hook in a linked worktree inherits GIT_DIR without GIT_WORK_TREE, which git
    reads as "the current directory is the top of the work tree". `-C` changes that
    directory, so the work tree is pinned to the one the variable was meant for.
    """
    git_dir = os.environ.get("GIT_DIR")
    if not git_dir or os.environ.get("GIT_WORK_TREE"):
        return None
    cwd = os.getcwd()
    return {**os.environ, "GIT_DIR": os.path.join(cwd, git_dir), "GIT_WORK_TREE": cwd}


def _git(root: Path, *args: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=False, env=_git_env()
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    except OSError as exc:
        raise GitError(f"git cannot be run: {exc.strerror or exc}") from exc
    if proc.returncode != 0:
        detail = os.fsdecode(proc.stderr).strip() or f"exit {proc.returncode}"
        raise GitError(f"git {' '.join(args)} failed in {root}: {detail}")
    return [os.fsdecode(part) for part in proc.stdout.split(b"\0") if part]


def work_tree_top(directory: Path) -> Path | None:
    """The top level of the git work tree containing `directory`, or None."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            env=_git_env(),
        )
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        # A git that exists but cannot run (not executable) is an error, not "outside a work tree".
        raise GitError(f"git cannot be run: {exc.strerror or exc}") from exc
    if proc.returncode != 0:
        return None
    return Path(os.fsdecode(proc.stdout).rstrip("\n")).resolve()


def is_top_level(root: Path) -> bool:
    """True when `root` is itself the top level of a git work tree.

    A temporary directory nested inside some other work tree is not one.
    """
    return work_tree_top(root) == root.resolve()


def _walk(root: Path) -> list[str]:
    found: list[str] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        base = Path(current).relative_to(root)
        found.extend((base / name).as_posix() for name in names)
    return sorted(found)


def list_files(root: Path, read: str, *, fallback: bool = True) -> Listing:
    """List the files a tool reads.

    `read` is "tracked" or "worktree". Without a work tree rooted at `root` the
    filesystem is walked when `fallback` is true; otherwise that is an error.
    A failing git command inside a work tree is always an error.
    """
    if not is_top_level(root):
        if not fallback:
            raise GitError(f"{root} is not the top level of a git work tree")
        return Listing(_walk(root), "filesystem")
    if read == "tracked":
        listed = sorted(set(_git(root, "ls-files", "-z")))
        present = [p for p in listed if os.path.lexists(root / p)]
        gone = sorted(set(listed) - set(present))
        return Listing(present, "tracked", gone)
    everything = set(_git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"))
    deleted = set(_git(root, "ls-files", "-z", "--deleted"))
    return Listing(sorted(everything - deleted), "worktree")


def list_untracked(root: Path) -> list[str]:
    """Untracked, non-ignored files, for layout checks. Empty outside a work tree."""
    if not is_top_level(root):
        return []
    return sorted(set(_git(root, "ls-files", "-z", "--others", "--exclude-standard")))


def tracked_under(root: Path, path: str) -> list[str]:
    """Tracked files at or under `path` (relative to `root`), from the index.

    Never lists untracked or ignored files. `root` must be the top level of a work tree.
    """
    if not is_top_level(root):
        raise GitError(f"{root} is not the top level of a git work tree")
    return sorted(set(_git(root, "--literal-pathspecs", "ls-files", "-z", "--", path)))


def tracked_in(directory: Path) -> list[str] | None:
    """Tracked files below `directory`, relative to it; None when it is outside any work tree."""
    if work_tree_top(directory) is None:
        return None
    return sorted(set(_git(directory, "ls-files", "-z")))
