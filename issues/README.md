# Issues

The work items of mgtk-repo-utils: defects, requests and tasks the
maintainers have taken on. This is a file-based tracker read and checked by
the tools of this repository; GitHub Issues stays open as the way to report
something from outside, and an accepted report becomes an item here.

## Layout

- `items/<id>.md` — one item per file. A file never moves, whatever its
  status.
- `README.md` (this file) — the conventions and the generated view.
- `_template.md` — the template for a new item.

Anything else directly under `issues/` fails `check`.

## Conventions

- The file name is `YYYYMMDD_slug.md`; the `id` in the frontmatter equals the
  stem.
- `status` is one of `open | in_progress | blocked | deferred | closed |
  wont_fix`; `priority` is `high | medium | low`; `type` is
  `bug | feature | task | question`.
- Closing an item sets `status: closed` and `closed:` (a date); the file
  stays where it is.
- Items point at each other by id (`blocked_by`, `blocks`, `related` in the
  frontmatter; `issue <id>` in the text), never by path.
- Items are written in English and describe the tool, its design and its
  releases. They do not name the repositories that run the tool, the people
  who asked, or anything else that is not the tool's own concern; a
  consumer's own tracker records its side and may point here, never the
  other way round.
- To find items, search the frontmatter and the text (for example
  `rg -l '^status: open' issues/items`).

## View (generated)

The view below is generated from the frontmatter by `issues-view`
(configured in `mgtk-repo-utils.toml`). **Do not edit it by hand, and do not
keep another list or status table of the items anywhere.** The pre-commit
hook regenerates it when a status changes (`prek install` once per clone;
`pre-commit install` also works); CI verifies that it matches.

<!-- BEGIN GENERATED: issues-active -->
active 0 (in_progress 0, blocked 0, open 0) / deferred 0 / done 1 (closed 1, wont_fix 0)
<!-- END GENERATED: issues-active -->
