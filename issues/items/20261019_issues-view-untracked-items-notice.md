---
id: 20261019_issues-view-untracked-items-notice
title: "issues-view: say when untracked item files are left out of the view under read = tracked"
type: feature
status: closed
priority: medium
created: 2026-10-19
closed: 2026-10-19
closed_by: "issues-view names an untracked item in a warning under read = tracked (design revision 6.2)"
labels: [issues-view]
blocked_by: []
blocks: []
related: []
---

# issues-view: say when untracked item files are left out of the view under read = tracked

## Summary

With `read = "tracked"` (the default), `issues-view` and the `check` run
that includes it report success while an item file sits untracked in the
items directory, and the generated view omits that item without any notice.

## Context

Seen between 2026-10-07 and 2026-10-16 in three repositories that run the
released hooks: an item written by another working session arrived as an
untracked file, the view hook (`prek run --all-files`) returned Passed, and
the view changed only after the file was staged with `git add`. People
reading "Passed" took it to mean the view was current.

Reading only the index under a pre-commit hook is a deliberate design:
`docs/design.md:128-131` records that a repository whose hook regenerates the
view must read tracked files only, and that a newly filed issue is then
missing from the view. This item asks about what the person running the check
can see, not about that choice.

Sender's view, to consult and not to follow: a notice (not a failure) naming
the untracked item files, printed only when they exist under
`read = "tracked"`. A notice that never fails would keep the tracked-only read,
and would respect that a layout check failing on untracked files stops every
unrelated commit in a repository that has just received a delivered issue file
(`docs/design.md:132-133`).

Validated on 2026-10-19 against 3776abb4d857d6d5f7976806f66eec4810809fcb:
every cited line holds as described, and `uv run mgtk-repo-utils check`
passed and counted one item while this file sat untracked.

## Problem

Observed at 3776abb4d857d6d5f7976806f66eec4810809fcb:

- `packages/core/src/mgtk_repo_utils/files.py:105-109`: with `read =
  "tracked"` only the output of `git ls-files -z` is listed.
- `packages/issues-view/src/mgtk_repo_utils_issues_view/config.py:83`: the
  default of `read` is `"tracked"`.
- `packages/issues-view/src/mgtk_repo_utils_issues_view/__init__.py:141-144`:
  untracked files are collected and pass the layout check, but only paths in
  the tracked listing are loaded as items.
- `packages/issues-view/src/mgtk_repo_utils_issues_view/__init__.py:352-353`
  and `docs/design.md:856-860`: the one existing signal for an untracked
  item, `untracked_rows`, applies only under `read = "worktree"`.

So under the default, a well-named untracked item produces no output at all:
not an error, not a warning, and not a line in the summary. The run is
indistinguishable from one where no such file exists, and the view is stale
relative to the working tree until the file is staged.

## Acceptance criteria

- [x] A run under `read = "tracked"` makes it visible to the person reading
      the output when the items directory holds untracked, non-ignored item
      files that the view does not include.
- [x] A run with no such files prints nothing new and keeps its exit code.

## References

- `docs/design.md` lines 128-133, 856-860, 887-890
- `packages/core/src/mgtk_repo_utils/files.py:94-121`
- `packages/issues-view/src/mgtk_repo_utils_issues_view/__init__.py:137-144, 352-361`
