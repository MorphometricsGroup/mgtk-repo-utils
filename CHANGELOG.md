# Changelog

mgtk-repo-utils succeeds **repo-kit** (`MorphometricsGroup/repo-kit`, releases
0.1.0 to 0.3.0, archived), which shipped the same tools as a copy committed into
each consumer. Its history, and the design revisions that led here, are in that
repository; `docs/design.md` here continues its design document.

Each release marks any change to generated output (view layout, wording), so
that consumers regenerate in the same commit that moves their pin, and lists
every change to a distribution, a hook id, a subcommand or an option.

## 0.1.0

Generated output: unchanged from repo-kit 0.3.0.

The first release: the tools of repo-kit 0.3.0, repackaged as one distribution
installed from this repository's git URL (design revision 5 and 5.1) instead of
a copy committed into each consumer.

- One uv workspace: `mgtk-repo-utils-core`, one distribution per tool
  (`-issues-view`, `-freeze-lint`, `-link-check`, `-clone`) discovered through
  the entry-point group `mgtk_repo_utils.tools`, and the root distribution
  `mgtk-repo-utils` that provides the command, `check` and `tools`. All carry
  one version.
- The repository is a pre-commit hook repository (`.pre-commit-hooks.yaml`):
  hooks `mgtk-repo-utils-issues-view`, `mgtk-repo-utils-freeze-lint`,
  `mgtk-repo-utils-link-check`, `mgtk-repo-utils-check`. A consumer pins by
  commit (`rev`), and `check` includes `pin`, which fails on any other pin.
- The configuration file is `mgtk-repo-utils.toml`; its `schema` stays 1 and
  its tables and keys are those of repo-kit 0.3.0; `requires` restarts at
  `"0.1"`.
- PyYAML is a declared dependency (of the clone tools and of `pin`); nothing
  is stdlib-only by rule any more.
- Removed with the copy: `verify`, `install.sh`, `SOURCE.md`,
  `MANIFEST.sha256`, the `repo-kit-verify` hook id, the payload README, the
  `python3 -B <copy>` entry and its Python-version guard, and the exclusions
  of the copy from formatters and lints.
- Messages that said "this copy" now say "this release"; the PyYAML remedy
  names the installation instead of a copy's path.

A consumer of repo-kit 0.3.x moves in one commit: delete the copy, rename
`repo-kit.toml` to `mgtk-repo-utils.toml` and set `requires = "0.1"`, replace
its `repo: local` hooks by this hook repository at a frozen `rev`, rewrite its
recipes from `python3 -B vendor/repo-kit <tool>` to `mgtk-repo-utils <tool>`,
and drop the copy's exclusions. Views are unchanged.
