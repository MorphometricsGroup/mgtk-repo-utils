# mgtk-repo-utils

Repository-maintenance tools that several repositories need in the same form:

- **issues-view** — a generated view over file-based issues, with layout and
  frontmatter checks
- **freeze-lint** — tracked files under a path, checked against an allowlist
- **link-check** — relative Markdown links and heading anchors
- **resolve** and **clone** — read the repository's registries of other
  repositories, map each entry, a named set of entries, or an entry the
  registry does not hold yet to the place the registry declares for its
  clone (`resolve`, which writes nothing; `--format json` for scripts),
  check those declarations (`resolve --check`), and place the clones there
  (`clone`, one entry or a set)
- **check** — every configured tool above (in check mode), then **pin**

A consumer configures the tools with one file, `mgtk-repo-utils.toml`, at its
root, and pins one release of this repository by commit in its hook
configuration. Nothing of mgtk-repo-utils is committed into a consumer.

`clone` is the one tool that writes outside the repository and uses the
network. It writes only strictly inside the roots the configuration declares,
fetches only the URLs it allows, creates no root, never overwrites or repairs
an existing checkout (`--update` only fast-forwards one from its checked
`origin`), and never receives or selects a credential: git runs with the
machine's own keys and configuration. Run it by hand or from a recipe, not from
a hook or CI.

## Using it from hooks (the pin)

This repository is a pre-commit hook repository. In `.pre-commit-config.yaml`
(or `prek.toml`):

```yaml
repos:
  - repo: <this repository's git URL>
    rev: <full commit>  # frozen: v0.1.0
    hooks:
      - id: mgtk-repo-utils-issues-view
        args: [--write]
      - id: mgtk-repo-utils-check
```

`rev` is a full commit, written by `prek update --freeze` (pre-commit:
`autoupdate --freeze`). A tag can be moved and needs the network to resolve; a
commit is immutable and is what the hook runner caches, so a release once
fetched keeps running on that machine. `check` fails when the pin is anything
else. Hook ids: `mgtk-repo-utils-issues-view`, `mgtk-repo-utils-freeze-lint`,
`mgtk-repo-utils-link-check`, `mgtk-repo-utils-check`.

Running the pinned release by hand: `prek run mgtk-repo-utils-check --all-files`.

## Using it from a shell (the command)

The same distribution installs on a machine with uv:

```sh
uv tool install "git+https://github.com/MorphometricsGroup/mgtk-repo-utils@v0.1.0"
mgtk-repo-utils check
mgtk-repo-utils clone <id>
mgtk-repo-utils tools        # what this installation provides
```

The machine chooses the release; `requires` in the consumer's
`mgtk-repo-utils.toml` stops one that is older than the configuration needs.
A consumer writes no second pin for this path. `uvx --from "git+https://…@<ref>"
mgtk-repo-utils …` works too; with a tag or a branch it resolves the ref on
every run.

## Configuration

`mgtk-repo-utils.toml` at the repository root: `schema = 1`, optional
`requires = "0.1"` and `lang = "en" | "ja"`, then one table per tool that the
repository enables — `[issues]`, `[freeze]`, `[links]`, `[clone]`. A table of a
tool that is not installed is an unknown table; `mgtk-repo-utils tools` lists
what is installed. The keys are specified in [docs/design.md](docs/design.md)
(section 4, and 13 for `[clone]`).

## Predecessor

mgtk-repo-utils succeeds repo-kit (`MorphometricsGroup/repo-kit`, 0.1.0 to
0.3.0, archived), which shipped the same tools as a copy committed into each
consumer. A consumer of a repo-kit copy moves in one commit:
[docs/migrations/from-repo-kit.md](docs/migrations/from-repo-kit.md).

## Development

```sh
uv sync
uv run pytest -q
uv run mgtk-repo-utils --help
```

One distribution, `mgtk-repo-utils`, holds every package: `packages/core`
(configuration, reports, file listing, tool discovery), one directory per tool
under `packages/`, and `src/mgtk_repo_utils_cli` (the command). The directories
are the seams along which a tool could move to a repository of its own; until
then they ship together, and the root `pyproject.toml` installs with pip from
its metadata alone, which is what a pre-commit hook repository needs.

Work follows GitHub Flow with semi-linear merges: a feature branch and a
draft pull request into `main`; before merging, rebase the branch onto `main`
and tidy its history to the commits worth keeping, then merge with a merge
commit (the only merge method `main` accepts; the branch must be up to date
and the checks green). Commits follow Conventional Commits (`fix:`, `feat:`,
`feat!:` for a change consumers must act on); release-please turns them into
a release pull request that bumps the version in `pyproject.toml` and
`__init__.py` and writes CHANGELOG.md, and merging it creates the tag
`vX.Y.Z` and the GitHub release. The pull request's title is a plain
sentence, not a Conventional Commit: GitHub writes the title into the merge
commit's message, release-please parses it like any commit, and a `feat:`
title would enter the CHANGELOG a second time beside the commits it merges;
the merge commit cannot be amended afterwards. Large consumer-facing changes
get a page under `docs/migrations/`.

CI also scans every tracked file against a denylist of names that must never
appear here. The list is the repository secret `MGTK_REPO_UTILS_DENYLIST` (one
name per line), never a tracked file; `scripts/dev/scan_denylist.py` runs the
same scan locally with the variable set.

## Status

Released: see [CHANGELOG.md](CHANGELOG.md) for the current version. The design
is in [docs/design.md](docs/design.md).

## Issue tracking

Work items live in [issues/](issues/README.md), a file-based tracker read and
checked by this repository's own tools (the hooks run the pinned release, CI
the working tree). Items describe the tool, its design and its releases, in
English, and never name the repositories that run it. GitHub Issues is the
way to report something from outside; an accepted report becomes an item.

## Licence

Apache-2.0. Copyright (c) 2026 Koji Noshita and Morphometrics Group.
