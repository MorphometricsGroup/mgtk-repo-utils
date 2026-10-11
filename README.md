# mgtk-repo-utils

Repository-maintenance tools that several repositories need in the same form:

- **issues-view** — a generated view over file-based issues, with layout and
  frontmatter checks
- **freeze-lint** — tracked files under a path, checked against an allowlist
- **link-check** — relative Markdown links and heading anchors
- **resolve** and **clone** — read the repository's registries of other
  repositories, map each entry to the place the registry declares for its
  clone (`resolve`, which writes nothing), check those declarations
  (`resolve --check`), and place the clone there (`clone`)
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
uv tool install "git+ssh://git@<host>/<owner>/mgtk-repo-utils@v0.1.0"
mgtk-repo-utils check
mgtk-repo-utils clone <id>
mgtk-repo-utils tools        # what this installation provides
```

The machine chooses the release; `requires` in the consumer's
`mgtk-repo-utils.toml` stops one that is older than the configuration needs.
A consumer writes no second pin for this path. `uvx --from "git+ssh://…@<ref>"
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
consumer. A consumer of a repo-kit copy moves in one commit; the
[CHANGELOG](CHANGELOG.md) entry for 0.1.0 lists what it rewrites.

## Development

```sh
uv sync
uv run pytest -q
uv run mgtk-repo-utils --help
```

The repository is a uv workspace: `packages/core` (configuration, reports,
file listing, tool discovery), one package per tool under `packages/`, and the
root distribution with the command. Every distribution carries the one version
of `packages/core/src/mgtk_repo_utils/__init__.py`; the tag equals it.

CI also scans every tracked file against a denylist of names that must never
appear here. The list is the repository secret `MGTK_REPO_UTILS_DENYLIST` (one
name per line), never a tracked file; `scripts/dev/scan_denylist.py` runs the
same scan locally with the variable set.

## Status

Released: see [CHANGELOG.md](CHANGELOG.md) for the current version. The design
is in [docs/design.md](docs/design.md).

## Issue tracking

This repository keeps no issue tracker and no `issues/` directory. Requests
and defects are tracked by its maintainers outside it.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
