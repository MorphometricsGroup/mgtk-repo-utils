# SPDX-License-Identifier: Apache-2.0
"""clone: put a declared repository at its destination (design sections 16 and 17).

The only tool that writes outside the repository and uses the network. Every git
call on a destination runs with the environment of design section 17: the
variables `git rev-parse --local-env-vars` lists are dropped, so a `GIT_DIR` or
`GIT_WORK_TREE` inherited from a hook cannot turn git onto the consumer's own
repository. The environment is read here for that and, through `registry.expand`,
for `HOME` and the root variables; nothing else is read for its value.
"""

from __future__ import annotations

import argparse
import functools
import os
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from mgtk_repo_utils.config import Config, add_common_options, load_for_tool
from mgtk_repo_utils.report import Report, ToolError, message

from . import registry
from .config import SCHEME_RE
from .registry import Entry, _show, clone_config

TOOL = "clone"

# They carry configuration, not a location (design section 17).
KEEP = frozenset({"GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT"})
DEFAULT_PORTS = {"ssh": 22, "https": 443}
SSH_SCHEMES = frozenset({"ssh", "git+ssh", "ssh+git"})


class _Fail(Exception):
    """A configuration or environment error, rendered in the configured language by `run`."""

    def __init__(self, msg_id: str, **params: object) -> None:
        super().__init__(msg_id)
        self.msg_id = msg_id
        self.params = params


# URLs


def _strip_path(path: str) -> str:
    """The path without one leading `/`, one trailing `/` and one trailing `.git`."""
    return path.removeprefix("/").removesuffix("/").removesuffix(".git")


def _reduce(url: str) -> tuple[tuple[str, ...], str | None]:
    """The comparison key of design section 16, and the SSH user the URL names (or None).

    Equal keys mean the same repository; the user is compared apart, by `same_url`.
    """
    if SCHEME_RE.match(url):
        try:
            parts = urlsplit(url)
            scheme, host, port, user = parts.scheme, parts.hostname, parts.port, parts.username
        except ValueError:
            return ("text", url.removesuffix("/")), None
        if scheme in DEFAULT_PORTS and host:
            kept = "" if port in (None, DEFAULT_PORTS[scheme]) else str(port)
            key = ("net", host, kept, _strip_path(parts.path), parts.query, parts.fragment)
            return key, (user or None) if scheme == "ssh" else None
        return ("text", url.removesuffix("/")), None
    head, colon, path = url.partition(":")
    if colon and head and "/" not in head:
        user, _, host = head.rpartition("@")
        return ("net", host.lower(), "", _strip_path(path), "", ""), user or None
    return ("text", url.removesuffix("/")), None


def same_url(first: str, second: str) -> bool:
    """Whether two URLs name the same repository (design section 16, URL comparison).

    When both are SSH spellings and both name a user, the users must be equal: two accounts
    on one host are two identities. `https` names no SSH user, so it is never compared.
    """
    (first_key, first_user), (second_key, second_user) = _reduce(first), _reduce(second)
    if first_key != second_key:
        return False
    return first_user is None or second_user is None or first_user == second_user


def mask(url: str) -> str:
    """The URL with a credential in its user part hidden, for every printed URL.

    A password is replaced; a user part without a password is a token, so it is replaced as
    a whole, except in the SSH family (`ssh`, `git+ssh`, `ssh+git`), where it is an account
    name and stays.
    """
    scheme = SCHEME_RE.match(url)
    if not scheme:
        return url
    rest = url[scheme.end() :]
    end = next((i for i, c in enumerate(rest) if c in "/?#"), len(rest))
    userinfo, at, host = rest[:end].rpartition("@")
    if not at:
        return url
    name, colon, _ = userinfo.partition(":")
    if colon:
        hidden = f"{name}:***"
    elif url[: scheme.end() - 3].lower() in SSH_SCHEMES:
        return url
    else:
        hidden = "***"
    return f"{url[: scheme.end()]}{hidden}@{host}{rest[end:]}"


def _shown_url(url: str) -> str:
    return _show(mask(url))


def _quoted(text: str) -> str:
    return shlex.quote(_show(text))


# git


@functools.cache
def _dropped_names() -> frozenset[str]:
    """The variables git lists as locating or shaping a repository, less `KEEP`."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = _run(["git", "rev-parse", "--local-env-vars"], clean, capture=True)
    if proc.returncode != 0:
        detail = _show(_first_line(proc.stderr)) or f"exit {proc.returncode}"
        raise _Fail("clone-git-env", detail=detail)
    names = frozenset(os.fsdecode(proc.stdout).split()) - KEEP
    if "GIT_DIR" not in names:  # an empty or foreign list would drop nothing: fail closed
        raise _Fail("clone-git-env", detail="GIT_DIR is not in its output")
    return names


def destination_env() -> dict[str, str]:
    """The environment for git calls on a destination (design section 17)."""
    dropped = _dropped_names()
    return {k: v for k, v in os.environ.items() if k not in dropped}


def _run(
    argv: list[str], env: dict[str, str], *, capture: bool
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(argv, env=env, capture_output=capture, check=False)
    except FileNotFoundError as exc:
        raise _Fail("clone-git-missing") from exc
    except OSError as exc:
        raise _Fail("clone-git-unrunnable", detail=exc.strerror or str(exc)) from exc


def _git(*args: str, capture: bool = True) -> subprocess.CompletedProcess[bytes]:
    return _run(["git", *args], destination_env(), capture=capture)


def _text(data: bytes | None) -> str:
    return os.fsdecode(data or b"")


def _first_line(data: bytes | None) -> str:
    lines = [line for line in _text(data).splitlines() if line.strip()]
    return lines[0] if lines else ""


# steps


def _lstat(path: str) -> bool:
    """Whether anything is at `path`; a dangling symlink counts as there."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise _Fail("clone-stat", path=_show(path), detail=exc.strerror) from exc
    return True


def _inside(path: Path, outer: Path) -> bool:
    return path != outer and path.is_relative_to(outer)


def _containment(
    entry: Entry, config: Config, dest: str, root_dir: str, present: bool
) -> tuple[str, dict[str, object]] | None:
    """Step 3: the problem, as a message id and parameters, or None when the destination is contained."""
    real_root = Path(os.path.realpath(root_dir))
    if present:
        real_dest = Path(os.path.realpath(dest))
    else:
        real_dest = Path(os.path.realpath(os.path.dirname(dest))) / os.path.basename(dest)
    if not _inside(real_dest, real_root):
        return "clone-escapes", {
            "dest": _show(dest),
            "real": _show(str(real_dest)),
            "root": entry.root,
            "real_root": _show(str(real_root)),
        }
    for name, text in clone_config(config).roots.items():
        if name == entry.root:
            continue
        try:
            other = Path(os.path.realpath(registry.expand(text, name, None, config.lang)))
        except ToolError:
            continue  # a root this machine does not define cannot be in the way
        # Folded: where the filesystem ignores case, `realpath` keeps the spelling it was given.
        if Path(registry._fold(str(other))).is_relative_to(registry._fold(str(real_dest))):
            return "clone-other-root", {
                "dest": _show(dest),
                "real": _show(str(real_dest)),
                "other": name,
                "real_other": _show(str(other)),
            }
    return None


def _existing(
    entry: Entry, dest: str, root_dir: str, update: bool, report: Report
) -> str | None:
    """Step 5: report the problem and return None, or return what was done (`present`, `updated`)."""
    assert entry.id is not None and entry.url is not None
    ident = _show(entry.id)
    shown = _show(dest)
    quoted = _quoted(dest)

    def problem(msg_id: str, **params: object) -> None:
        report.error(msg_id, ident, dest=shown, **params)

    if not os.path.isdir(dest):
        problem("clone-dangling" if os.path.islink(dest) else "clone-file")
        return None
    probe = _git("-C", dest, "rev-parse", "--show-prefix", "--is-inside-work-tree")
    # `--show-prefix` alone is empty in a bare repository and inside a git directory too.
    if not (probe.returncode == 0 and _text(probe.stdout).split("\n")[:2] == ["", "true"]):
        _not_a_checkout(dest, probe, report, ident)
        return None

    # A linked worktree or a `--separate-git-dir` checkout keeps its repository data elsewhere,
    # and `pull` would write there.
    dirs = _git("-C", dest, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir")
    paths = _text(dirs.stdout).split("\n")[:-1]
    if dirs.returncode != 0 or len(paths) != 2:
        detail = _show(_first_line(dirs.stderr)) or message(
            report.lang, "detail-git-exit", code=dirs.returncode
        )
        problem("clone-git-failed", args="rev-parse --git-dir --git-common-dir", detail=detail)
        return None
    real_root = Path(os.path.realpath(root_dir))
    for path in paths:
        if not _inside(Path(os.path.realpath(path)), real_root):
            problem("clone-gitdir-outside", root=entry.root, gitdir=_show(path))
            return None

    declared = _shown_url(entry.url)
    declared_quoted = _quoted(mask(entry.url))
    configured = _git("-C", dest, "config", "--get-all", "remote.origin.url")
    found = _text(configured.stdout).splitlines()
    if configured.returncode not in (0, 1):
        detail = _show(_first_line(configured.stderr)) or f"exit {configured.returncode}"
        problem("clone-git-failed", args="config --get-all remote.origin.url", detail=detail)
        return None
    if not found:
        problem("clone-no-origin", url=declared, qdest=quoted, qurl=declared_quoted)
        return None
    if len(found) > 1:
        shown_found = "`, `".join(_shown_url(value) for value in found)
        problem(
            "clone-origin-several",
            found=shown_found,
            url=declared,
            qdest=quoted,
            qurl=declared_quoted,
        )
        return None
    if not same_url(found[0], entry.url):
        problem(
            "clone-origin-differs",
            found=_shown_url(found[0]),
            url=declared,
            qdest=quoted,
            qurl=declared_quoted,
        )
        return None
    if not update:
        return "present"
    pull = _git("-C", dest, "pull", "--ff-only", "--no-recurse-submodules", "origin", capture=False)
    if pull.returncode != 0:
        problem("clone-pull-failed", code=pull.returncode)
        return None
    return "updated"


def _not_a_checkout(
    dest: str, probe: subprocess.CompletedProcess[bytes], report: Report, ident: str
) -> None:
    shown = _show(dest)
    try:
        empty = not os.listdir(dest)
    except OSError:
        empty = False
    if empty:
        report.error("clone-empty", ident, dest=shown, quoted=_quoted(dest))
        return
    lines = _text(probe.stdout).split("\n")
    if probe.returncode != 0:
        detail = _show(_first_line(probe.stderr)) or message(report.lang, "detail-git-exit", code=probe.returncode)
    elif lines[1:2] == ["true"]:
        detail = message(report.lang, "detail-inside-worktree")
    else:
        bare = _git("-C", dest, "rev-parse", "--is-bare-repository")
        if _text(bare.stdout).strip() == "true":
            report.error("clone-bare", ident, dest=shown)
            return
        detail = message(report.lang, "detail-inside-git-dir")
    report.error("clone-not-checkout", ident, dest=shown, detail=detail)


def run(config: Config, name: str, update: bool) -> tuple[list[str], int]:
    """Handle one id; returns the report lines and the exit code (a ToolError is exit 2)."""
    try:
        return _handle(config, name, update)
    except _Fail as exc:
        raise ToolError(message(config.lang, exc.msg_id, **exc.params)) from exc


def _handle(config: Config, name: str, update: bool) -> tuple[list[str], int]:
    lang = config.lang
    resolution = registry.load(config, TOOL)
    entry = resolution.find(name)
    if entry is None:
        raise ToolError(message(lang, "resolve-unknown", id=name))
    attached = resolution.problems_for(entry)
    # An alias collision can exclude an entry; its problems say so, so they come first.
    if entry.excluded and not attached:
        raise ToolError(message(lang, "resolve-excluded", id=name, source=entry.source.name))
    report = Report(TOOL, lang)

    # 1. Declaration
    if attached:
        report.items.extend(attached)
        return report.lines(), report.exit_code
    assert entry.id is not None and entry.url is not None
    ident = _show(entry.id)

    # 2. Root
    dest = registry.expand_destination(entry, clone_config(config).roots, lang=lang)
    root_dir = registry.expand(clone_config(config).roots[entry.root], entry.root, None, lang)
    if not os.path.isdir(root_dir):
        raise ToolError(
            message(
                lang,
                "clone-root-missing",
                root=entry.root,
                path=_show(root_dir),
                quoted=_quoted(root_dir),
            )
        )
    parent = os.path.dirname(dest)
    if entry.deviation is not None and not os.path.isdir(parent):
        raise ToolError(
            message(lang, "clone-parent-missing", path=_show(parent), quoted=_quoted(parent))
        )

    # 3. Containment
    present = _lstat(dest)
    escape = _containment(entry, config, dest, root_dir, present)
    if escape is not None:
        report.error(escape[0], ident, **escape[1])
        return report.lines(), report.exit_code

    # 4. Missing destination
    if not present:
        proc = _git("clone", "--", entry.url, dest, capture=False)
        if proc.returncode != 0:
            report.error("clone-failed", ident, code=proc.returncode)
            return report.lines(), report.exit_code
        done: str | None = "cloned"
    else:
        # 5. Existing destination
        done = _existing(entry, dest, root_dir, update, report)
    if done is None:
        return report.lines(), report.exit_code
    summary = message(lang, f"summary-clone-{done}", id=ident, dest=_show(dest))
    return report.lines(summary), report.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgtk-repo-utils clone",
        description="Clone the repository an entry of the registries declared in [clone] names "
        "into its destination, or with --update fast-forward a checkout that is already "
        "there. Writes only strictly inside a declared root; uses the network and the "
        "machine's git credentials.",
    )
    parser.add_argument("id", help="an id or alias of an entry")
    parser.add_argument(
        "--update",
        action="store_true",
        help="fast-forward an existing checkout whose origin matches the declaration "
        "(git pull --ff-only --no-recurse-submodules origin)",
    )
    add_common_options(parser)
    return parser


def main(argv: list[str], cwd: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_for_tool(args, TOOL, cwd or Path.cwd())
        lines, code = run(config, args.id, args.update)
    except ToolError as exc:
        print(f"mgtk-repo-utils: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return code
