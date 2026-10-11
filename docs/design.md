# mgtk-repo-utils — design

Status: revision 6.1 (2026-10-11), current for mgtk-repo-utils from 0.1.1; the
routing, selection sets and read-only queries of sections 13 to 16 are
designed for 0.2.0 and implemented on the branch that releases it.
mgtk-repo-utils is the successor of **repo-kit**
(`MorphometricsGroup/repo-kit`, releases 0.1.0 to 0.3.0, which shipped as a
copy committed into each consumer); this document continues repo-kit's design
document. Where it says repo-kit it means the predecessor and its releases;
where it says mgtk-repo-utils it means the tool from its 0.1.0 on. Revision
4.1 is current for repo-kit v0.3.0. Revision 5 changes how the tools are
packaged and distributed (sections 1 to 3 and 10 to 12); the tools themselves
(sections 5 to 9 and 13 to 17) are unchanged except where a sentence named the
copy. Sections 13 to 17 are implemented in repo-kit 0.3.0, except the keys and
the flag marked as later.

## Overview

mgtk-repo-utils is a small collection of repository-maintenance tools that several
repositories need in the same form. Most of them inspect or generate files
inside the repository that runs them: a generated view over file-based issues
(with its layout and frontmatter checks), a lint that freezes a tracked path
against an allowlist, and a Markdown relative-link checker. Their results
appear in that repository's `git diff`, and they need no network and no
credentials. Two tools read the repository's registries — files that list
other repositories. `resolve` maps each listed repository to the place the
registry declares for its clone and writes nothing. `clone` places the clone
there: it is the one tool that writes outside the repository, over the
network, with whatever credentials the machine provides.

All of them ship as one Python distribution, `mgtk-repo-utils`, installed from this
repository's git URL at a tagged release. A consumer's commit hooks run it
through a hook runner (prek or pre-commit) that pins the release by commit in
the consumer's hook configuration, and people run the same distribution, at a
release their machine chooses, with `uvx` or `uv tool install`. Nothing of
mgtk-repo-utils is committed into a consumer: the consumer holds one configuration
file and one pin. As repo-kit (0.1.0 to 0.3.x) the tools shipped as a copy
committed into each consumer (alternative J).

This document decides how the code is shared, what a consumer receives, how a
consumer configures it, and what each tool does.

## Goals

- One implementation of each tool, used by every consumer, so an improvement
  lands once and no repository redevelops it.
- Per-repository differences expressed as configuration values: vocabularies,
  id shape, title source, language, read scope, severity, view shape.
- The tools run from a consumer's commit hooks, from its CI and from a
  person's shell, at a release the consumer pins in one place. The pin is a
  commit, so the release a consumer runs is the one it declares, and a release
  once fetched stays runnable from the cache that fetched it. Dependencies are
  declared, not avoided: a tool may depend on a library where that is simpler
  than rewriting it, and the whole collection installs with its dependencies
  in one step.
- A registry's declared placement — which repository is cloned where — is
  executed by one implementation, while every authority stays outside the
  tool: the consumer declares where the tool may write and what it may fetch,
  the machine's environment holds the credentials, and whoever runs the
  command decides each run (section 17).
- A consumer cannot run an unpinned or tag-pinned release from its hooks
  without `check` saying so (section 10).
- Publishable later, in parts. No distribution names an internal project, path
  or vocabulary; no tool knows which consumer runs it; and nothing in the code
  tells a tool meant for one organisation from a tool meant for anyone. Where
  a tool needs authority — a registry, a credential, a place to write — the
  consumer's configuration and the machine's environment grant it (section
  17). The boundary between internal and public is drawn there, not in the
  code, so a tool can move to a public repository without changing.
- Reachable by repositories generated from a copier template through the same
  pin as every other consumer: the template renders the hook configuration and
  `mgtk-repo-utils.toml`, and holds no code of mgtk-repo-utils.

## Non-goals

- Validating each repository's full issue schema. A repository that already
  validates its frontmatter elsewhere can switch the vocabulary checks off.
- Validating each repository's own registries and their invariants. Those
  data differ per repository. `resolve --check` checks only what placement
  needs — ids, URLs, destinations — and nothing of a registry's own schema.
- Preparing a machine. `clone` creates no root directory and installs nothing;
  a missing root is an error that names the command to create it. Cloning
  everything a machine should hold is that machine's bootstrap, which the
  consumer's own procedures own.
- Handling credentials. `clone` never receives, reads or selects a key or a
  token; a repository that needs a particular key arranges it in its own
  environment, and git receives it from there.
- Repairing a checkout. A checkout whose remote differs from its declaration
  is reported, never rewritten.
- Finding clones that no registry declares. `resolve` maps declarations to
  paths; it does not survey the disk.
- Detecting that a newer release exists. `prek update` does that for the
  consumer that asks; `pin` only proves that the pin is a commit.
- Repository-specific conventions (a ban on a particular character, a
  reference syntax). They stay in the repository that holds them.
- Moving files. The `issues/items/` layout is a recommendation, not a
  requirement; mgtk-repo-utils supports both flat and `items/` trackers, and a
  repository that adopts `items/` migrates in a commit of its own. No
  migration helper is planned.
- Protection against deliberate tampering. A commit pin is as strong as the
  consumer's access to this repository; `pin` checks the pin's form, not who
  moved it.
- Publishing to a package index, now. The distributions are built to be
  publishable, and nothing is published: every consumer installs from this
  repository's git URL. A public index, and the split of this repository that
  would precede it, are decided when a tool is first wanted outside the
  organisation.
- Being added to a consumer's project as a library (`uv add`). A consumer
  pins and runs a release; it does not import mgtk-repo-utils. A consumer that is a
  Python project may lock it in its own project; how that lock then serves as
  the pin is an open question, not designed here.
- Keeping a consumer runnable from a plain clone with nothing installed. The
  consumer's hook runner, and a person's `uv`, fetch the pinned release once
  per machine; a clone on a machine that has never fetched it needs this
  repository, or a mirror the consumer declares, to be reachable (alternative
  J, risks).

## Background

On 2026-10-06 three repositories adopted the same issue-tracker shape — the
`issues/` root is a view, `issues/items/<id>.md` holds the data and never
moves by status, a generated block in `issues/README.md` lists the active
issues — and a fourth decided to. Each of the three wrote its own generator
(one a fork of another, one independent), and the fourth was about to vendor
one and port it again for its copier template. The same day showed what a
shared tool has to absorb:

- Read scope depends on who runs the generator. A repository whose pre-commit
  hook regenerates the view must read tracked files only; a repository whose
  maintainer runs the generator by hand before committing must read the working
  tree, or a newly filed issue is missing from the view.
- A layout check that fails on untracked files stops every unrelated commit in
  a repository that has just received a delivered issue file from elsewhere.
- YAML ends an unquoted value at ` #`, silently. Two such truncations passed
  every check that day, and one of them reached a generated view
  (`title: X #7 …` rendered as `X`). A census of existing trackers finds 24
  such lines in one repository and 1 among the template's adopters.
- The same rule — a tracked path frozen against an allowlist — has three
  implementations in three repositories, differing only in message language
  and in whether a missing allowlisted file also fails.

Precedents inside the organisation:

- A typesetting-theme repository: the producer decides what is copied
  (`scripts/install.sh`), the destination is replaced wholesale,
  project-specific settings live in a file the project owns. It has no stamp
  and no drift check; on 2026-10-06 its three copier-generated consumers held
  0.2.8 while the theme was at v0.3.1, and nothing reported it.
- The copier template distinguishes shape (distributed by copier and followed
  by `copier update`) from content (vendored, pinned per project). Its
  generated ADR index uses the marker grammar
  `<!-- BEGIN GENERATED: <name> -->` / `<!-- END GENERATED: <name> -->`, which
  other tools already treat as protocol when each marker sits alone on its line.
- A code-sharing convention elsewhere classifies hand copies as in-sync,
  diverged-by-design or needs-sync and stamps each with its origin.

### Background of the clone tools (revision 4)

A consumer that keeps a registry of repositories also declares where each
listed repository is cloned on a working machine: a default root per kind of
entry, the clone named after the repository, and a per-entry field for a
declared deviation. On 2026-10-07 two consumers stood at opposite ends:

- One executes its declarations with scripts of its own: a resolver that maps
  a name to its registry, destination and URL, and a clone script that calls
  it. It reads three registries. Their ids are a name plus aliases in one and a
  slug in the other two; the directory is the name in one and the URL's
  basename in the others (a slug `x-y` names a repository `x_y`). Its roots are
  environment variables set per machine; a field routes the entries of one
  registry to one of two roots; its bulk clone is filtered by two fields, one
  of which has a default for an absent value. The script creates a missing
  root.
- The other declares the same kind of rules in a schema and in prose and has
  no means to execute them. Its entries are `owner/name` slugs under several
  keys of one file, nested in lists of mappings; the directory is the name
  part; the root depends on the key. Four entries declare deviations, two of
  them outside every root on purpose. Every clone on its machines was placed
  by hand, and a deviation field left equal to the default is found only by
  reading the file.

A third registry of the same shape is expected. The registry differs per
consumer while the mechanism does not — the same split as the issue view — so
each consumer writing its own scripts is the redevelopment the first goal
exists to remove. These registries nest mappings in lists, which the
frontmatter reader of section 6 does not read.

### Background of the distribution change (revision 5)

Five days after the first adoption, the copy's running costs were visible in
every consumer: a commit per consumer per release to replace the copy;
exclusions of the copy from every formatter and content lint; the `verify`,
`SOURCE.md` and `MANIFEST.sha256` machinery, which exists only because a copy
can be edited; and a few hundred kilobytes of someone else's code in each
diff. The maintainer asked for the tools to become a command that installs
with `uvx`, configured declaratively, modular, distributed from this
repository. Two premises of alternative A's rejection had changed:

- No consumer needs to run the tools from a plain clone with nothing
  installed. Every consumer runs its hooks through prek or pre-commit, which
  install hook environments, and every machine that runs them has `uv`.
- Everything the tools hold is internal for now, and the public-bound template
  does not yet depend on them from outside the organisation. The boundary
  between internal and public is therefore not drawn today; the design keeps
  it drawable (goals) rather than drawing it.

Three things were measured before deciding, with uv 0.12.24 and prek 0.5.5
on a throwaway workspace of two packages:

- A workspace member installs alone from the repository's git URL with
  `#subdirectory=`, and a sibling it depends on through `workspace = true`
  resolves to the same commit. A consumer `pyproject.toml` without a
  `[project]` table locks such a dependency, and the lock records the commit.
- Once fetched, a release keeps running after the repository is gone: a prek
  hook environment (prek holds a full clone of the hook repository, and
  `--refresh` does not need the origin), a `uv` lock, and `uvx` pinned by a
  commit all do. `uvx` pinned by a tag does not — it resolves the tag on
  every run, offline included.
- A hook repository whose root is a workspace without a package installs
  nothing, so the hook's entry is not found; the root must itself be an
  installable package.

Not measured, and left to the first consumer that moves (rollout step 11): a
private git URL over SSH from a hook with no terminal, and `#subdirectory=`
against the hosted repository rather than a local one.

**Name, home and history (revision 5.1, the same day).** With the copy gone,
the tool holds nothing that only the organisation may see: every
consumer-specific fact is in the consumer's configuration, every credential in
the machine's environment (goals), and all consumers today are inside the
organisation. The maintainer therefore moved the tool's governance to the
organisation that hosts it, and with it the name: the organisation's naming
guide gives shared tools the prefix `mgtk-` and two to four words
(`mgtk-visualization-utils` is one of its examples), so the tool is
**mgtk-repo-utils**, and the command, the configuration file, the hook ids and
the distributions take that name (sections 1 to 3). The repository starts
afresh — `MorphometricsGroup/mgtk-repo-utils` receives the finished tree as
its first commit, without repo-kit's history — so the scan of that history
that publication would have required is not needed; what remains is a review
of the tree itself before it leaves the workshop (rollout step 9). The version
restarts at 0.1.0 and the CHANGELOG starts clean, naming repo-kit as the
predecessor and the archived repository as the place of the earlier history.
The repository is public (revision 5.2, the same day): the review of step 9
found nothing in the tree that belongs to one organisation, the code takes
every authority from configuration and environment, and a public repository
spares every consumer the credentials a private hook repository would need in
CI. The organisation's permission rule for `mgtk-` tools (members write,
affiliates read) still applies to who may change it. repo-kit's repository
stays readable, with a pointer, until every consumer of its 0.3.x copies has
moved, and is archived then.

## Alternatives considered

### A. One package per tool, pinned through pre-commit or a uv git dependency
- **Approach:** a dedicated repository for the issue view, consumed as a
  pre-commit hook repository (`repo:` + `rev:`) or a pinned git dependency.
- **Pros:** no copy, so nothing to verify; standard update path
  (`pre-commit autoupdate`).
- **Cons:** a repository per tool; consumers without pre-commit or without a uv
  project need a second path; every gate needs network access to install; a
  private source cannot back a public template.
- **Why not chosen:** the tools are a few hundred lines each, share one owner
  and one cadence, and at least one consumer must stay runnable from a plain
  clone. A collection with one tag is cheaper.
- **Re-evaluated (2026-10-11, revision 5): chosen, in the form of section 2.**
  Of the cons, two were premises that no longer hold (background of revision
  5); one — network at the gate — is answered by the pin being a commit and
  by the hook runner's cache; and one — a repository per tool — is not what
  the alternative requires: one repository holds several installable
  distributions and one hook repository. What was right in the rejection
  stays: the tools share one owner and one cadence, so they share one version
  and one tag (section 12).

### B. Reference implementation kept in a standards repository, copied and owned
- **Approach:** a private repository that records the organisation's
  standards holds the reference; each consumer copies it, stamps the origin
  and edits freely.
- **Pros:** no new repository; full freedom per consumer.
- **Cons:** improvements do not propagate unless someone diffs by hand; drift
  is accepted by design. That repository holds internal names and stays
  private, so a public consumer cannot point at it, and holding code that
  others run would widen its role.
- **Why not chosen:** the differences found are values, not structure, so
  configuration covers them; and the public-bound template needs a source it
  can name.

### C. Contract only
- **Approach:** fix the marker grammar, view format and layout rules in a
  written contract; each repository keeps its own implementation.
- **Pros:** no shared code, no release process.
- **Cons:** every repository still writes and maintains the same code; the
  contract needs its own conformance check.
- **Why not chosen:** it leaves the redevelopment this design exists to remove.

### D. A script in a personal tools repository, called at run time
- **Approach:** consumers' hooks call a script deployed under the user's home.
- **Cons:** invisible to CI, not reproducible from a clone, and a change there
  silently changes every consumer's gate.
- **Why not chosen:** fails the clone/CI/offline goal outright.

Alternatives E to I concern the clone tools of revision 4.

### E. Each consumer keeps its own resolver and clone script
- **Approach:** the consumer that has scripts keeps them; the other writes its
  own, and the third consumer another.
- **Pros:** no new kind of tool in mgtk-repo-utils; each script fits its registry
  exactly.
- **Cons:** the same resolution, containment checks and handling of existing
  checkouts are written three times, and the safety properties (no write
  outside a root, no URL read as an option) are only as good as each copy.
- **Why not chosen:** the differences between the registries are values —
  which keys hold entries, which field is the id, which root — so configuration
  covers them, as it does for the issue view.

### F. A shared tool that also selects credentials
- **Approach:** the configuration names a key or a token per entry or per
  owner, and the tool hands it to git.
- **Pros:** one place shows which credential reaches which repository.
- **Cons:** every copy becomes a place that handles secrets, so each consumer
  that adopts one widens the credential scope of its own repository; and the
  configuration would decide what the machine's environment already decides.
- **Why not chosen:** credentials stay with the machine — an SSH agent, a
  credential helper, a per-repository environment — and the tool calls git
  with the environment as it is (section 17).

### G. Filters and routing as expressions
- **Approach:** a small query language in the configuration: predicates in the
  entry path, wildcards, computed roots.
- **Pros:** one configuration form could express any registry.
- **Cons:** this is the risk of the configuration growing into a language; the
  registries met so far need none of it.
- **Why not chosen:** entry paths are dots and `[]` only, and filtering is by
  listed values (`exclude`, and the conditions of `sets` in section 13).

### H. A static check only, cloning left to people
- **Approach:** mgtk-repo-utils checks the declarations (unique ids, deviations
  inside roots) and people clone by hand.
- **Pros:** the tools stay inside the repository; no network, no credentials.
- **Cons:** the declarations are still not executed, and the hand-placed clone
  is what drifts from them.
- **Why not chosen:** executing the declared placement is the point; the
  static check comes with it (section 15).

### I. `resolve` only, cloning left to each consumer's recipe
- **Approach:** mgtk-repo-utils ships `resolve` and its static check; a consumer's
  recipe reads the line `resolve` prints and runs `git clone -- "$url" "$dest"`
  itself.
- **Pros:** the copy stays a set of tools that read and inspect — no network,
  no credentials, no write outside the repository — so publishing it exposes
  no more than before revision 4. The recipe is two lines, and `resolve`'s
  output is already meant for scripts (section 14).
- **Cons:** what makes a clone safe lies outside those two lines: a missing
  root is reported rather than created, the destination stays inside its root
  after symlinks, an existing directory is recognised as the declared checkout
  or reported, `--update` fetches only from the remote it checked, and git does
  not inherit the variables that point at the consumer's own repository
  (sections 16 and 17). Each recipe would carry these again or go without them.
  The design review of revision 4 found most of its defects in exactly this
  part.
- **Why not chosen:** those rules are the part worth sharing, and they are the
  same for every consumer. The price is the one the chosen approach names: the
  copy contains a tool that writes outside the repository and uses the network,
  confined by `roots` and `urls` and fixed by the tests of section 17.

Alternatives J to M concern the distribution change of revision 5. The
measurements in its background apply to each.

### J. A copy committed into each consumer (the approach of revisions 1 to 4)
- **Approach:** section 2 of revision 4.1: a tagged release copied wholesale
  into a directory the consumer commits, stamped with its origin, verified
  against a manifest, configured by one file.
- **Pros:** every clone runs the tools with `python3` alone, offline, with no
  cache and no credential; the release a consumer runs is visible in its tree
  and auditable in its diff; nothing is fetched at commit time.
- **Cons:** every consumer carries and replaces the copy; every formatter and
  lint in every consumer excludes it; `verify` and the manifest exist only to
  catch edits to it; the copy is a second home for mgtk-repo-utils's code, kept
  current by hand in each consumer; the constraints on the payload (no YAML
  file, no dotfile, no `lib` or `build` directory, stdlib only) come from
  living inside other trees.
- **Why not chosen now:** the plain-clone premise has been given up, and the
  remaining pros are met another way: the pin is a commit in the consumer's
  tree, and a fetched release stays runnable from the hook runner's cache.
  Where a consumer needs the release obtainable without this repository, it
  declares a mirror; that is the consumer's decision and its own record,
  not mgtk-repo-utils's.

### K. A copy kept, built and replaced by machine
- **Approach:** keep J and remove its friction: ship the payload as one
  zipapp file, so that there is one blob to exclude and to diff, and add a
  `self-update <tag>` command or a bump script that replaces it and commits.
- **Pros:** keeps every pro of J; the diff noise shrinks to one file.
- **Cons:** keeps the second home and the per-consumer replacement; a zipapp
  is not reviewable in a diff; `verify` is still needed; the plain-clone
  property it preserves is no longer wanted.
- **Why not chosen:** it lowers the cost of a model whose benefit has been
  given up.

### L. A plugin framework with a private repository for internal tools
- **Approach:** a public core that holds no tools and discovers them through
  an entry-point group, as repo-review does; public tools in the public
  repository; tools that need internal authority in a private repository that
  depends on core.
- **Pros:** the boundary between internal and public is a package boundary,
  enforced by where the code lives; a consumer picks tools by what it
  installs.
- **Cons:** two repositories from the first day, when nothing is public and no
  tool is internal in its code: every tool takes its authority from
  configuration and environment (goals). The split would precede the thing it
  separates.
- **Why not chosen as a whole:** its mechanism is adopted — one distribution
  per tool, discovered through an entry-point group, core naming no tool
  (sections 1 and 3) — so that the split costs a directory move and a pin
  change when a tool is first wanted outside. The second repository is not
  created until then.

### M. Hooks only, no command
- **Approach:** the hook repository is the only interface; a consumer's hook
  configuration names the hooks it wants, `prek run <id>` runs one by hand,
  and no command is installed on any machine.
- **Pros:** one pin per consumer by construction; nothing to install by hand.
- **Cons:** `clone` does not fit a hook — it takes an argument, uses the
  network and writes outside the repository, and section 11 keeps it out of
  hooks and CI — and neither does any future tool that runs with arguments or
  outside a git repository.
- **Why not chosen alone:** the hook repository is the gate and the only pin a
  consumer writes; the command exists for what a hook cannot be and for a
  person's shell, and it is the same distribution at a release the machine
  chooses (section 2).

## Chosen approach: one repository, one release, two ways in; a pin per consumer, authority in configuration

mgtk-repo-utils is one repository holding several Python distributions in a uv
workspace: a core that loads configuration, reports, lists files and discovers
tools; one distribution per tool; and the repository root, which is itself the
distribution `mgtk-repo-utils` — a package that depends on every tool, provides the
`mgtk-repo-utils` command and the `check` and `pin` commands, and is what a consumer
installs. All of them carry one version and are released by one tag.
Dependencies are declared in the usual way (PyYAML is one), and nothing is
stdlib-only by rule.

A consumer uses a release in two ways, from the same distribution:

- **Hooks and CI** install it through the hook runner: the repository root is
  a pre-commit hook repository, the consumer's hook configuration names it
  with a `rev` that is a commit, and `check` fails where it is not (section
  10). This is the consumer's one pin.
- **People and `clone`** install it on the machine with `uvx` or
  `uv tool install`, at whatever release the machine chooses; `requires` in
  `mgtk-repo-utils.toml` stops a release older than the configuration needs, and a
  consumer writes no second pin for this path (section 11).

Per-consumer differences stay configuration values in `mgtk-repo-utils.toml`, as
before, and structural differences that configuration cannot express stay
outside mgtk-repo-utils as the consumer's own code. Which tools run is decided by
which tables the file has; which tools are installed is decided by which
distribution is installed, and today there is one. Internal and public are not
distinguished anywhere in the code: a tool reads the registries, roots and
URLs the consumer declares and runs git with the machine's credentials
(section 17), so moving a tool to a public repository changes a pin, not the
tool.

Consequences, both ways:

- Easier: nothing of mgtk-repo-utils lives in a consumer's tree, so there is no copy
  to replace, exclude or verify; a release reaches a consumer by a one-line
  change that `prek update --freeze` writes; a tool may use a library; the
  payload constraints that came from living inside other trees fall away; a
  consumer's CI runs the same hook environment as its commits.
- Harder: a consumer needs its hook runner, and a person's machine `uv`, to
  obtain a release — a clone on a machine that has never fetched it needs
  this repository or a declared mirror to be reachable (and, while the
  repository was private, a consumer's CI needed read access as for any
  private dependency); the pin must be a commit, which a check now enforces;
  mgtk-repo-utils is a uv
  workspace with a build where it was a directory of files, so a packaging
  step stands between a change and a consumer.

The clone tools follow the same approach: the data — each registry — stays in
its consumer, and the mechanism is shared. A `[clone]` table names the
registry files, the keys that hold entries, the roots the tools may write
into and the URLs they may fetch; `resolve` maps an entry to its destination
without writing, and `clone` writes. Easier: one implementation of the
containment rules serves every consumer, and a declared placement is executed
instead of read. Harder: mgtk-repo-utils now ships a tool that writes outside the
repository, uses the network and depends on PyYAML, and its configuration
surface grows by a table.

## Detailed design

### 1. Repository layout

Revision 5. The repository is a uv workspace; its root is the distribution a
consumer installs. Until 0.3.x the layout was a `payload/` directory copied
wholesale (revision 4.1, alternative J).

```text
mgtk-repo-utils/
  LICENSE                      Apache-2.0
  README.md                    usage, wiring recipes
  CHANGELOG.md                 per release; flags releases that change generated output
  docs/design.md               this document
  pyproject.toml               the distribution `mgtk-repo-utils`: depends on every tool at the
                               same commit (`workspace = true`), provides the command,
                               declares the workspace members
  uv.lock                      the workspace lock (development only; a consumer resolves its own)
  .pre-commit-hooks.yaml       the hook repository: one hook per tool, and `mgtk-repo-utils-check` (section 2)
  src/mgtk_repo_utils_cli/
    __init__.py                the `mgtk-repo-utils` command: options, tool dispatch, `tools`, `--version`
    check.py                   `check`: every installed tool whose table is present, then `pin`
    pin.py                     `pin` (section 10)
  packages/
    core/                      distribution `mgtk-repo-utils-core`, import package `mgtk_repo_utils`
      src/mgtk_repo_utils/
        __init__.py            __version__ (the one version of the workspace, section 12)
        config.py              mgtk-repo-utils.toml loading and validation; tool tables registered at discovery
        files.py               file listing: tracked | worktree | filesystem
        frontmatter.py         strict frontmatter reader
        slug.py                heading slugs (port of github-slugger)
        patterns.py            glob matching
        report.py              problem collection; the core's own message catalogue (en, ja)
        tool.py                the tool protocol and entry-point discovery (section 3)
    issues-view/               distribution `mgtk-repo-utils-issues-view`, import package `mgtk_repo_utils_issues_view`
    freeze-lint/               distribution `mgtk-repo-utils-freeze-lint`, import package `mgtk_repo_utils_freeze_lint`
    link-check/                distribution `mgtk-repo-utils-link-check`, import package `mgtk_repo_utils_link_check`
    clone/                     distribution `mgtk-repo-utils-clone`, import package `mgtk_repo_utils_clone`:
                               registry reading, `resolve`, `clone` (sections 13 to 17); depends on PyYAML
  tests/                       unit tests and fixtures (not shipped)
```

Each tool distribution depends on `mgtk-repo-utils-core`, carries its own
`pyproject.toml` with the version of section 12, and registers one entry in
the entry-point group `mgtk_repo_utils.tools` (section 3). Its message catalogue
(en, ja) travels with it. The core distribution holds what every tool needs
and nothing a consumer runs by itself.

Constraints on the code, each from publication or from the goals:

- No internal name: no distribution, module, message, test or fixture names
  an internal project, path or vocabulary. The maintainer scans the repository
  against a denylist kept outside it, since the list itself names what must
  not be published; from mgtk-repo-utils 0.1.0 the same scan runs in this repository's CI
  against the list supplied as a secret, never as a tracked file, because
  nothing of mgtk-repo-utils lives in a consumer's tree any more for the consumer's
  own lints to catch.
- Every source file starts with `# SPDX-License-Identifier: Apache-2.0`.
- No character in emitted text that content lints commonly reject (the
  section sign, U+00A7, is the known case): consumers lint their generated
  views, and a tool must not be what fails them.
- One version: every distribution's version equals `mgtk_repo_utils.__version__`,
  and the tag equals it (section 12). A test checks the workspace.
- Core imports no tool, and no tool imports another: a tool reaches core
  through its modules, and core reaches a tool only through the entry-point
  group. A test parses the imports.

Dropped with the copy, since they came from living inside other trees: no
YAML file, no dotfile, no `lib`/`lib64`/`build`/`dist` directory, no Markdown
link leaving the payload, stdlib only, `-B` and the `__main__.py` guard.

**Correction (2026-10-11, revision 5.3).** The layout above described one
distribution per tool, resolved to one commit through uv workspace sources.
The first adopter outside this repository's own hook runner measured, the
same day, that pre-commit installs a `language: python` hook repository with
`pip install .`, which reads only the standard metadata: it could not
resolve `mgtk-repo-utils-core` and the tool distributions (`No matching
distribution found for mgtk-repo-utils-clone`), while prek, which builds hook
environments with uv, could. The repository therefore ships **one
distribution**, `mgtk-repo-utils`: its wheel holds every package
(`src/mgtk_repo_utils_cli` and the five `packages/*/src/*` packages), its only
dependency is PyYAML, and the per-tool `pyproject.toml` files and the
workspace are gone. The directories and the entry-point discovery stay: a
tool that is to live elsewhere becomes its own distribution when it moves,
not before. Section 2's "members alone" is withdrawn, and section 12's
lockstep is one version by construction. A packaging test checks that the
root metadata names no internal distribution and that the wheel lists every
package, and CI installs the root with pip into a fresh virtual environment,
the path uv does not exercise.

### 2. Distribution: the hook repository and the command

Revision 5. There is no copy. A consumer obtains a release in one of two
ways, both from this repository's git URL at a tag or a commit. (For repo-kit
this section specified `scripts/install.sh`, `SOURCE.md` and
`MANIFEST.sha256`; revision 4.1 has it.)

**Hook repository.** The repository root carries `.pre-commit-hooks.yaml`
with one hook per tool and one for `check`:

```yaml
- id: mgtk-repo-utils-issues-view
  name: mgtk-repo-utils issues-view
  entry: mgtk-repo-utils issues-view
  language: python
  pass_filenames: false
  always_run: true
- id: mgtk-repo-utils-freeze-lint
  name: mgtk-repo-utils freeze-lint
  entry: mgtk-repo-utils freeze-lint
  language: python
  pass_filenames: false
  always_run: true
- id: mgtk-repo-utils-link-check
  name: mgtk-repo-utils link-check
  entry: mgtk-repo-utils link-check
  language: python
  pass_filenames: false
  always_run: true
- id: mgtk-repo-utils-check
  name: mgtk-repo-utils check
  entry: mgtk-repo-utils check
  language: python
  pass_filenames: false
  always_run: true
```

A `language: python` hook installs the hook repository's root with pip or
uv. The root is the distribution `mgtk-repo-utils`, whose dependencies are the tool
distributions at the same commit: their `workspace = true` sources resolve to
that commit when the root is installed from a clone or from a git URL
(measured, background of revision 5). The consumer writes, in
`.pre-commit-config.yaml` or `prek.toml`:

```yaml
repos:
  - repo: <mgtk-repo-utils URL>
    rev: 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b  # frozen: v0.1.0
    hooks:
      - id: mgtk-repo-utils-issues-view
        args: [--write]
      - id: mgtk-repo-utils-check
```

`rev` is a full commit. A tag can be moved, and a tool that resolves a tag
needs the network; a commit is immutable and is the key under which the hook
runner caches the release, so a release once fetched keeps running on that
machine after this repository is unreachable (measured). `prek update
--freeze` writes this form and keeps the `# frozen:` comment current; `pin`
fails on any other form (section 10). Hook ids are fixed across releases
(section 11).

**Command.** The same distribution installs on a machine:

```sh
uv tool install "git+https://github.com/MorphometricsGroup/mgtk-repo-utils@v0.1.0"    # or @<commit>
mgtk-repo-utils check
mgtk-repo-utils clone <id>
uvx --from "git+https://github.com/MorphometricsGroup/mgtk-repo-utils@<commit>" mgtk-repo-utils check
```

The machine chooses the release; the consumer's `requires` (section 4) stops
one that is older than its configuration needs. A consumer writes no pin for
this path (section 11). `uvx` with a tag or a branch resolves it on every run
and needs the network each time; a recipe that must work offline installs the
tool or names a commit.

**Members alone.** Each tool distribution installs alone from the same URL
with `#subdirectory=packages/<tool>`, its dependency on core resolved to the
same commit. No consumer needs this today; it is what makes moving a tool to
another repository a pin change (alternative L).
**Correction (2026-10-11, revision 5.3):** withdrawn. There is one
distribution (section 1); nothing installs with `#subdirectory=`. Moving a
tool to another repository remains a directory move, followed by giving it
a `pyproject.toml` of its own there.

**Authentication.** The repository is public, so reading it needs no
credential; the `https` URL works from any hook runner, CI or machine. Where
a consumer names an SSH URL instead, the keys are the machine's, as for any
dependency; the tools receive none (section 17). An unattended caller — a
hook with no terminal, CI, an agent — sets `GIT_TERMINAL_PROMPT=0` and an SSH
command with `-o BatchMode=yes` so that a missing credential fails instead of
waiting. A consumer whose gate must survive this repository being
unreachable from a fresh machine declares a mirror in its own records and names
it in the `repo:` line; `pin` finds the entry by its hook ids, not by its URL.

Installing from a release archive and from a package index are not designed
(non-goals).

### 3. Running a tool

Revision 5. The command is a console script of the distribution `mgtk-repo-utils`:

```sh
mgtk-repo-utils issues-view --check
mgtk-repo-utils freeze-lint
mgtk-repo-utils link-check
mgtk-repo-utils pin                             # section 10
mgtk-repo-utils check
mgtk-repo-utils resolve <id>                    # sections 13 to 17
mgtk-repo-utils clone <id>
mgtk-repo-utils tools                           # the tools this installation provides, with their tables
mgtk-repo-utils --version
```

In repo-kit the same tools ran as `python3 -B <copy> <tool>`; the tool names,
options, outputs and exit codes are unchanged, so a recipe changes only its
prefix.

**Discovery.** The command finds tools through the entry-point group
`mgtk_repo_utils.tools`. Each tool distribution registers one entry whose value is
an object of the protocol in `mgtk_repo_utils.tool`: the tool's name (the
subcommand), the name and schema of its configuration table (section 4), its
message catalogue (en, ja), and `run(config, args) -> int`. Core names no
tool; `mgtk-repo-utils tools` lists what is installed, so a consumer can see why a
table is unknown. A tool whose table the configuration lacks is disabled, as
before. Two installed distributions registering the same tool name is an
error that names both (exit 2); it does not arise with the one distribution
of today.

`check` runs every installed tool whose table is present (`issues-view` in
`--check` mode, and `resolve --check` for `[clone]`), then `pin`, prints each
tool's report in that order, and exits with the highest exit code among them.
A tool that stops with a usage or configuration error — a registry file
missing, `freeze-lint` outside a work tree — prints its error and counts as
2, and `check` still runs the tools after it and `pin`; before 0.3.0 the first
such error ended `check`. It never runs `clone`. It is the single manual entry
for a repository that has neither CI nor a validation recipe, and the
aggregate step for one that has a recipe.

The distributions declare `requires-python = ">=3.11"`; the hook runner and
`uv` choose an interpreter that satisfies it, and mgtk-repo-utils has no version
guard of its own. Python writes no bytecode into a consumer's tree, since
nothing of mgtk-repo-utils lives there.

Common options:

- `--root <path>`: the repository root. Default: the top level of the git work
  tree containing the current directory; outside any work tree, the current
  directory.
- `--config <path>`: default `<root>/mgtk-repo-utils.toml`. Every path in the
  configuration is relative to the root. An alternative file runs a tool once
  without enabling it in the repository's own configuration — for example
  `link-check` while validating a migration.

Exit codes, all tools: `0` no problem (warnings allowed); `1` problems found
(stale view, lint failure, broken link, a pin that is not a commit, a
declaration that does
not resolve, a checkout that differs from its declaration, a failed clone or
pull); `2` usage or configuration error, git or PyYAML missing
or not runnable where a tool needs it, a destination root that does not exist or names an
unset variable, a declared deviation whose parent directory does not exist, a
`HOME` that is unset or not absolute where `~` must be expanded.

`--root` is the repository whose configuration and registries are read. The
directories `clone` writes into are called destination roots (`roots` in
section 13) to keep the two apart.

Output: problems and warnings go to standard output, one per line as
`<path>[:<line>]: <message>`, after a header `<tool>: <n> problem(s)` or
`<tool>: <n> warning(s)`; success prints `<tool>: ok` with a short count.
Usage and configuration errors go to standard error. Messages come from a
catalogue in English or Japanese, and every message for a rejected input names
its remedy (for an unquoted ` #` or `: `: quote the value).

### 4. Configuration: `mgtk-repo-utils.toml`

Read with `tomllib`. Unknown keys and unknown tables are errors (exit 2), so a
typo cannot silently disable a check; the message names the running release's
version, so an older release reading a newer key is recognisable. Values are
type-checked (vocabulary arrays must hold strings). A tool whose table is
absent is disabled, and running it is an error; `pin` has no table and is
always available (until 0.3.x, `verify` was). `resolve` and `clone` share the
`[clone]` table, specified in section 13. From revision 5 the tables are
declared by the tools: core knows `schema`, `requires` and `lang`, and each
tool registers its table's name and schema at discovery (section 3), so a
table of a tool that is not installed is an unknown table, and the message
says so and names `mgtk-repo-utils tools`.

```toml
schema = 1                 # configuration schema version; required
requires = "0.1"           # optional: minimum mgtk-repo-utils version this file needs
lang = "ja"                # message language: "en" | "ja"

[issues]
dir = "issues"
items = "items"                    # "" for a flat tracker: items live in `dir`
template = "_template.md"          # or "TEMPLATE.md"
read = "tracked"                   # "tracked" | "worktree"
untracked = "warn"                 # severity of problems whose file is untracked
untracked_rows = "warn"            # severity of a view row for an untracked item (worktree only)
id_pattern = '\d{8}_[a-z0-9-]+'    # full match against the file stem, ASCII
id_field = "required"              # "required" | "absent" (stem is the id)
title = "field"                    # "field" | "field-or-h1"
items_allow = [".gitkeep"]         # extra names allowed among the items

[issues.status]
active = ["in_progress", "blocked", "open"]   # order = section order
deferred = ["deferred"]
terminal = ["closed", "wont_fix"]
check = true                                  # false: unknown statuses warn and count as "other"

[issues.fields]
priority = ["critical", "high", "medium", "low"]   # [] = not checked; order = sort order
type = ["bug", "feature", "task", "chore", "question"]
on_terminal = ["closed", "closed_by"]              # required (non-empty) when terminal
closed_only_when_terminal = true                   # non-null `closed` on a non-terminal status is an error

[issues.views."README.md"]
marker = "issues-active"                           # [a-z0-9-]+
lang = "ja"                                        # view language, defaults to the top-level lang
show = ["counts", "active", "deferred"]
sections = true                                    # false: one table with a status column
link = "issue"                                     # the column that links to the item: "issue" | "title"
columns = ["issue", "title", "priority", "created"]
extra_columns = { blocked = ["blocked_by"] }       # per status
sort = ["priority", "created"]
group_by = ""                                      # e.g. "target"
empty = "nothing"                                  # region when no item: "nothing" | "counts"

[freeze]
paths = [".vscode"]
allow = []
mode = "subset"       # "subset": extra tracked files fail | "exact": extra or missing fail
reason = ""           # appended to the failure message

[links]
read = "tracked"      # "tracked" | "worktree"
untracked = "warn"    # severity of problems in untracked files
anchors = true        # check #fragments against target headings
exclude = ["archive/**"]           # globs (`*`, `?`, `**`) over root-relative paths
ignore_targets = ['^\$']           # regexes, searched in the raw link target
```

The block above is an example, not the defaults. Defaults when a key is
absent:

- `lang = "en"`; `read = "tracked"`; `untracked = "warn"` (both tables);
  `untracked_rows = "warn"`.
- `[issues]`: `dir = "issues"`, `items = "items"`, `template = "_template.md"`,
  `id_pattern = '\d{8}_[a-z0-9-]+'`, `id_field = "required"`,
  `title = "field"`, `items_allow = []`.
- `[issues.status]`: the six values shown, `check = true`.
- `[issues.fields]`: `priority = []`, `type = []`, `on_terminal = []`,
  `closed_only_when_terminal = false` — nothing beyond what the view needs is
  checked unless asked for.
- Views: none unless declared. A declared view defaults to `lang` of the file,
  `show = ["counts", "active", "deferred"]`, `sections = true`,
  `link = "issue"`, `columns = ["issue", "title", "created"]`,
  `extra_columns = {}`,
  `sort = ["created"]`, `group_by = ""`, `empty = "nothing"`.
- `[freeze]`: `allow = []`, `mode = "subset"`, `reason = ""`; `paths` required.
- `[links]`: `anchors = false`, `exclude = []`, `ignore_targets = []`.

**Deliberate defaults (revision 5.1).** The defaults above, and the few
things no key changes, come from the repositories the tools were first
written for, and are kept as they are rather than generalised: the id
pattern `\d{8}_[a-z0-9-]+`, the `items/` directory and `_template.md`, the
status vocabulary `in_progress` / `blocked` / `open` / `deferred` / `closed` /
`wont_fix`, the fixed frontmatter keys `id`, `title`, `status` and `created`
(with `created` a required date, `closed` a date or null and `blocked_by` a
list; section 6), the `###` / `####` heading levels of a view and its place
directly inside the issues directory (section 7), and the Japanese
orthography of emitted text (`，`, `／`, `（）`, `件`). A repository with other
conventions sets the keys that exist; the fixed frontmatter shapes and the
orthography are the two a repository cannot change today, and they are open
questions below.

`untracked` means one thing in both tables: the severity of a problem *in* a
file that is untracked. Under `read = "tracked"` the only such problems are
layout problems; under `read = "worktree"` they include frontmatter and link
problems in untracked files. `untracked_rows` is a separate matter: a view row
that points at an untracked item, which is the normal intermediate state of a
hand-regenerated tracker between `--write` and staging, and is therefore a
warning unless a repository asks for more.

### 5. File listing (shared)

- `tracked`: `git ls-files -z` — the index, which is what the commit will
  contain. A path listed but deleted from the working tree is skipped with a
  warning.
- `worktree`: `git ls-files -z --cached --others --exclude-standard`, minus
  `git ls-files -z --deleted`.
- Filesystem fallback, for `issues-view` and `link-check` only: used when the
  root is not the top level of a git work tree (`git -C <root> rev-parse
  --show-toplevel` fails, or names another directory — a test's temporary
  directory inside some other repository). The walk skips dot-directories and
  `__pycache__`. Inside a work tree, a failing git command is an error, never a
  fallback.
- `freeze-lint` requires a work tree; outside one it exits 2.
- Git is run with `-C <directory>`. A hook in a linked worktree inherits
  `GIT_DIR` without `GIT_WORK_TREE`, which git reads as "the current directory
  is the top of the work tree"; `-C` would move that top into that directory and list
  the whole repository as its contents. When `GIT_DIR` is set and
  `GIT_WORK_TREE` is not, every git call therefore pins `GIT_WORK_TREE` to the
  process's working directory (and makes a relative `GIT_DIR` absolute against
  it), which is what the inherited variable meant. These rules hold for calls
  on the repository being checked; git calls on a clone destination follow
  section 17 instead.
- Layout checks always also look at untracked, non-ignored files and report
  them with the `untracked` severity. A file becomes tracked when it is staged,
  so a misplaced file that is a warning while untracked is an error once
  staged.

### 6. Frontmatter reader

A frontmatter block is the text between a first line `---` and the next line
`---`. A leading BOM is removed and CRLF is read as LF. The reader accepts a
strict subset of YAML, normalises values by the shape of the key, and rejects
everything else with a line number.

**Keys the tools read, and their shape.** A key is read only when the
configuration needs it; every other key is unknown and handled as below.

| Key | Shape | Read when |
|---|---|---|
| `status`, `created` | scalar, date | always |
| `id` | scalar | always (compared with the stem) |
| `title` | scalar | always (`field-or-h1` falls back to the first heading) |
| `priority`, `type` | scalar | its vocabulary is non-empty, or a view names it |
| `closed` | date or null | `closed_only_when_terminal`, or named in `on_terminal` |
| `blocked_by` | list | a view names it |
| any other key named in `on_terminal` or in a view's `columns`, `extra_columns`, `sort` or `group_by` | scalar or list, as written | so named |

With the defaults, for example, `closed_by` is not read: a value of it that
the reader would reject is only a warning (see unknown keys below).

**Accepted forms:**

- `key: value` at column 0, `key` matching `[A-Za-z_][A-Za-z0-9_-]*`.
- Plain scalars, which may continue on following lines indented more than the
  key (folded with single spaces, as YAML does).
- Single-quoted (`''` escape) and double-quoted (`\"`, `\\`, `\n`, `\t`
  escapes) scalars, which may continue over following lines, folded as YAML
  does.
- Block scalars `|`, `|-`, `>`, `>-` (no indentation indicator, no `+`).
- Flow lists `[a, b, "c d"]` of scalars, on one line.
- Block lists: `key:` followed by `- item` lines indented more than the key;
  items are scalars of any accepted scalar form.
- Full-line comments. A trailing comment only after a value that is
  syntactically closed — after `]`, after a closing quote, or after an empty
  value — separated by one or more spaces.

**Rejected (error):**

- A plain scalar containing `#` preceded by a space or a tab. YAML would end
  the value there silently; quoting it is the remedy.
- A plain scalar containing `: ` or ending in `:`, or starting with one of
  `` ` @ % & * ! ``; a closing quote followed directly by anything but spaces,
  a comment or the end of the line (`"a"#c`).
- Tabs in indentation or before a comment, duplicate keys, anchors, aliases,
  tags, nested flow collections, a block list item at the key's own indentation
  (`key:` then `- a` at column 0).
- A date-shaped key whose value is not a valid calendar date.

**Normalisation by shape:**

- Scalar keys keep the text as written (numbers and `true`/`false` stay
  strings).
- Date keys parse `YYYY-MM-DD`; `closed` also accepts null.
- List keys: null, an empty value, or a list whose only lines are comments
  read as `[]`; a scalar where a list is expected is an error.
- A key absent and a key present with null are the same for every rule
  (`closed: null` on an open issue is not "closed present").

**Unknown keys** are skipped together with every line indented under them
(nested mappings, lists, block scalars), with no interpretation beyond the
tab rule. The ` #` rule applies to unknown top-level plain scalars as a
warning.

**Conformance criterion.** For every key the tools read, on the frontmatter of
every issue in the current consumers and the template's adopters, the reader's
value equals PyYAML's after the normalisation above. The only permitted
differences are rejections listed above, each traceable to a rule. Measured
before revision 2: 24 plain scalars with ` #` in one repository and 1 in the
adopters (truncated by YAML today), and 1 plain scalar with `: ` (already a
YAML error).

**Correction (2026-10-06, after the first implementation).** Claimed: the
reader's value equals PyYAML's once numbers become strings. Measured: running
`tests/conformance/frontmatter_vs_pyyaml.py` over the current trackers, one
tracker whose ids are written `001` to `022` reads `"001"` in the reader and
`1` in PyYAML, whose integer conversion drops the leading zeros. What now
holds: a scalar keeps the text as written, which is the intended value; the
conformance comparison counts a PyYAML integer as equal when it equals the
reader's text read as an integer. The normalisation rules above are unchanged.

**Correction (2026-10-06, after the first implementation).** Claimed: unknown
keys are skipped, with only the ` #` rule applied to their top-level plain
scalars. Measured: the same run found a plain scalar containing `: ` under a
key the tools do not read; PyYAML rejects that whole document, while the
reader passed it in silence. What now holds: the ` #` rule and the `: ` rule
both apply to unknown top-level plain scalars, as warnings, because other YAML
readers fail on such a file.

### 7. issues-view

Responsibilities, in order:

1. **Layout.** The issues directory may contain only `README.md`, the template
   file, registered view files, and either the items directory or, for a flat
   tracker, the item files themselves. The items (in `items` or, if flat, in
   `dir`) are `<id>.md` files whose stem fully matches `id_pattern`, plus
   names in `items_allow`; no subdirectories.
2. **Frontmatter.** Each item has a frontmatter block the reader accepts.
   With `id_field = "required"`, `id` equals the stem; with `"absent"`, an
   `id` that is present must also equal the stem. A title is found: the
   `title` field, or for `field-or-h1` the first `# ` line after the
   frontmatter and outside fenced code. `created` is a date. `status` belongs
   to the configured classes (`check = true`). `priority` and `type` belong to
   their lists when those are non-empty. Every `on_terminal` key is non-empty
   on a terminal item, and `closed` is a date. `closed` is null or absent on a
   non-terminal item when `closed_only_when_terminal`.
3. **Views.** Each registered view file contains exactly one BEGIN line and,
   after it, exactly one END line for its `marker`. A marker line is a line
   whose content, stripped of surrounding whitespace, is exactly
   `<!-- BEGIN GENERATED: <marker> -->` or `<!-- END GENERATED: <marker> -->`.
   A marker quoted inside other text is not a marker.

**Region bytes (normative).** The writer replaces the lines strictly between
the two marker lines and nothing else:

```text
<BEGIN line>\n
<body line 1>\n
…
<body line n>\n
<END line>
```

With no body lines the region is exactly `<BEGIN line>\n<END line>`. Every byte
before the BEGIN line and after the END line, including the marker lines
themselves, is preserved. A template can ship the two marker lines adjacent and
pass `--check` on its first render.

**Body (with `sections = true`):**

```text
<counts line>
                                   (blank line)
### <status>
                                   (blank line)
| <label> | <label> | … |
|---|---|…|
| <cell> | <cell> | … |
                                   (blank line before the next section)
```

- `counts` emits the counts line first. Japanese:
  `active 5 件（in_progress 0，blocked 1，open 4）／deferred 4 件／終了 8 件（closed 8，wont_fix 0）`.
  English:
  `active 5 (in_progress 0, blocked 1, open 4) / deferred 4 / done 8 (closed 8, wont_fix 0)`.
  A class with no configured status is omitted; with `check = false`, a count
  of unknown statuses is appended as `other N`.
- `active` and `deferred` emit one section per status in class order; an empty
  section is omitted. Terminal items never appear except in the counts.
- With `group_by`, each section holds one `#### <value>` subsection per
  distinct value in ascending order, the missing value last as `(none)` /
  `（なし）`.
- With `sections = false`, one table holds every shown item, ordered by status
  class order and then by `sort`. It has a `status` column at the position
  where `columns` names `status`, or first when `columns` does not name it.
- Columns: `columns`, plus `extra_columns[<status>]` in that status's section.
  Labels: `issue`, `title` (ja: `タイトル`), `priority`, `created`, `status`,
  `blocked_by`, and any other key by its own name.
- Link: with `link = "issue"`, the `issue` cell is ``[`<id>`](<path>)``; with
  `link = "title"`, the `title` cell is `[<title>](<path>)` and `columns` may
  omit `issue`. `<path>` is the item path relative to the view file.
- Cells: `issue` without a link is `` `<id>` ``; a scalar is its text; a list joins its items with `<br>`,
  an item that fully matches `id_pattern` rendered in backticks; a date is
  `YYYY-MM-DD`. Every cell collapses whitespace runs (including line breaks) to
  one space, trims, and escapes `|` as `\|`. An empty cell is `—`.
- Sort: ascending by each key in `sort`, then by `id`. `priority` sorts by its
  vocabulary order and is ignored when the vocabulary is empty; any missing
  value sorts last.
- With no item to show: `empty = "nothing"` gives no body lines; `"counts"`
  gives the counts line only.

Modes:

- `--write`: regenerate every view whose region differs and exit 0, also after
  writing. A pre-commit or prek run fails when a hook modifies a file, whatever
  its exit code, so the commit still stops; a manual recipe does not report a
  failure for having regenerated.
- `--check`: write nothing; if a region differs, print a unified diff of the
  region and exit 1.
- Both: no view is written while a problem exists. Under `read = "worktree"`,
  a view row for an untracked item is reported with the `untracked_rows`
  severity: committed without the item, it would break in every other clone.

### 8. freeze-lint

Lists tracked files under each of `paths` with `git ls-files -z` — never
untracked or ignored files, which may legitimately hold local settings.
`subset` fails on any listed file absent from `allow`; `exact` also fails on
any `allow` entry not listed. The failure message names the files and appends
`reason`, so a repository's governance wording stays in its own configuration.

### 9. link-check

Scans Markdown files from the configured listing, minus `exclude` and the
copy. Recognised links: inline links and images `[text](target)` and
`![alt](target)`, and reference definitions `[label]: target`. Autolinks
(`<scheme:…>`, `<a@b>`) always carry a scheme or are e-mail addresses in
CommonMark and are external. Raw HTML is not checked.

For each link:

- skip text inside fenced code blocks (``` and ~~~) and inline code spans;
- skip targets with a URL scheme (`[a-z][a-z0-9+.-]*:`) and targets matching
  any `ignore_targets` regex;
- percent-decode the path and the fragment;
- resolve the path relative to the file and require it to be in the listing —
  not merely on disk — so a link to a file that will not be committed fails on
  the machine where it was written. A target that names a directory (it ends
  in `/`, or some listed file lies under it) resolves when at least one listed
  file lies under it; anchors are not checked for directories;
- with `anchors = true`, for targets that are Markdown files (or `#…` alone,
  meaning the same file), require the fragment to equal a heading slug in the
  target, or an `<a id>` / `<a name>` in it.

Heading slugs follow github-slugger, the published emulation of GitHub's
anchors: take the heading's text with inline markup removed (code spans keep
their content), trim it, lowercase it, delete every character the slugger's
generated regex deletes (Unicode punctuation except `-` and connector
punctuation, symbols, other numbers, controls, format characters, unassigned
code points, and separators other than U+0020, while keeping every Alphabetic
code point), replace each U+0020 with `-`, and suffix repeats `-1`, `-2`, …
skipping any slug already taken. `slug.py` ports the slugger's regex rather
than approximating it. Full-width spaces and punctuation are therefore deleted,
not hyphenated; full-width digits and letters are kept.

Generated view regions are scanned like any other text.

### 10. pin

Revision 5; replaces `verify`, which had no copy left to verify.

`pin` checks that the consumer's hook configuration pins mgtk-repo-utils by commit.
It reads `prek.toml`, `.pre-commit-config.yaml` or `.pre-commit-config.yml`
at the root — the first that exists, in prek's order — and looks at every
`repos` entry that lists a hook whose id begins with `mgtk-repo-utils-`. The ids are
the contract (section 11), so the entry is found whatever URL or mirror its
`repo:` line names.

Problems (exit 1):

- No entry lists a mgtk-repo-utils hook: the repository has no pin, and nothing
  declares which release its commits run.
- An entry's `rev` is not a full lowercase hexadecimal commit (40 or 64
  digits): a tag, a branch or a short commit can move or needs the network to
  resolve.
- Two entries pin different commits.

Warning:

- A `rev` whose line carries no `# frozen: <tag>` comment. Allowed, but the
  release is then not readable from the file; `prek update --freeze` writes
  the comment.

`pin` does not compare the pinned commit with the release that is running:
from a hook the two are equal by construction, and from a machine's
installation they differ by design (section 2), where `requires` covers the
gap. It reads no network and no other repository. A repository that runs
mgtk-repo-utils without hooks, from a recipe alone, has no pin and gets the first
problem; that is the point — such a repository has not declared a release.
The hook configuration is read with PyYAML, a dependency of the root
distribution; a `prek.toml` is read with `tomllib`; a file that cannot be
read is a configuration error (exit 2) that names it.

Formatters and linters in a consumer no longer exclude anything of mgtk-repo-utils;
the exclusions of 0.3.x are removed in the commit that moves the pin (section
12).

### 11. Wiring in consumers

Hook ids are fixed across releases so that a consumer's conformance lists can
name them: `mgtk-repo-utils-issues-view`, `mgtk-repo-utils-freeze-lint`,
`mgtk-repo-utils-link-check`, `mgtk-repo-utils-check`. In repo-kit they were
`repo-kit-*` (changed once, in its 0.2.0, with the rename from repo-lab);
`repo-kit-verify` has no successor, since there is no copy to verify, and
`mgtk-repo-utils-check` takes its place in hook configurations (`check`
includes `pin`). The ids are defined in this repository's
`.pre-commit-hooks.yaml` (section 2), not in each consumer's `repo: local`
block.

When to regenerate the view is the consumer's choice; mgtk-repo-utils supports three:

- **Hook regenerates** (`--write` in pre-commit): the hook rewrites the view
  and the commit stops once; staging the view and committing again completes
  it, like any auto-fixing hook. Needs the hook installed per clone.
- **Hook checks** (`--check` in pre-commit): the commit stops with a diff, and
  the author runs `--write`. The hook never writes.
- **Manual with a validation step**: the author runs `--write` before
  committing, and a validation recipe runs `--check`.

Where a repository has CI or a validation recipe, it runs `check` (or
`--check`, `pin` and the lints separately), which also covers clones where
the hook was never installed. A repository with neither relies on its hooks
alone; that is an allowed configuration, with the known gap that a clone
without the hook runs no check until someone runs `check` by hand.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: <mgtk-repo-utils URL>
    rev: 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b  # frozen: v0.1.0
    hooks:
      - id: mgtk-repo-utils-issues-view
        args: [--write]
        verbose: true     # warnings exit 0, and pre-commit hides a passing hook's output
      - id: mgtk-repo-utils-check
```

The three choices above differ only in `args` (`--write` or `--check`) and in
whether the `mgtk-repo-utils-issues-view` hook is listed at all. `mgtk-repo-utils-check`
covers every configured tool and `pin` in one hook; a consumer that wants
separate hook output lists `mgtk-repo-utils-freeze-lint` and `mgtk-repo-utils-link-check`
instead. prek behaves the same way as pre-commit for hooks that modify files
and for untracked files during its stash. Nothing is excluded from formatter
hooks any more.

A consumer that is a Python project pins the same way. Whether it may instead
lock mgtk-repo-utils in its own project and run the hooks from that environment, with
the lock as its pin, is an open question; until it is designed, every
consumer pins through the hook repository.

`clone` runs by hand or from a recipe, never from a hook or CI; its static
check reaches CI through `check`. That is a convention the tool does not
detect; where it is broken, the environment rule of section 17 keeps a
variable inherited from a hook from turning git onto the consumer's own
repository. An unattended caller, such as an agent, sets
`GIT_TERMINAL_PROMPT=0` and an SSH command with `-o BatchMode=yes` in the
environment it gives the tool, so that git fails instead of waiting for a
password, a passphrase or a host key; the tool passes both through. A
consumer with a `[clone]` table wraps `clone` in one recipe that calls the
machine's installation (section 2) — for example, with just:

```just
# Clone a repository the registry declares: just clone <id> [--update]
clone *args:
    mgtk-repo-utils clone {{args}}
```

The recipe writes no release of its own: `requires` in `mgtk-repo-utils.toml` stops
an installation older than the `[clone]` table needs, and the hook
configuration's `rev` stays the only pin in the repository. A consumer that
wants a recipe to run exactly the pinned release reads `rev` from its hook
configuration and passes it to `uvx --from <URL>@<rev>`; it does not write
the commit a second time.

### 12. Versioning and compatibility

- Tags `vMAJOR.MINOR.PATCH`; the tag always equals `v` + `__version__`, and
  from mgtk-repo-utils 0.1.0 every distribution in the workspace carries that version: one
  release, one tag, one `rev` for a consumer (lockstep versions). A change to
  one tool releases the workspace.
  **Correction (2026-10-11, revision 5.3):** one distribution (section 1), so
  one version by construction; `pyproject.toml` and `__init__.py` are kept
  equal by release-please (below).
- **Releases (revision 5.3).** Work follows GitHub Flow with semi-linear
  merges: a feature branch and a draft pull request into `main`, as long-lived
  as the work needs; before merging, the branch is rebased onto `main` and its
  history tidied to the commits worth keeping, and the pull request is merged
  with a merge commit. A ruleset on `main` enforces what GitHub can: a pull
  request, the CI checks passed on a branch that is up to date with `main`,
  merge commits as the only merge method, no force push, no deletion. Commits
  follow Conventional Commits; `feat!:` or a `BREAKING CHANGE:` footer marks a
  change consumers must act on, and a commit that changes generated output
  says so in its body. The pull request's title is a plain sentence and not
  a Conventional Commit: GitHub writes the title into the merge commit's
  message and release-please parses it like any commit, so a `feat:` title
  enters the CHANGELOG a second time beside the commits it merges, and the
  merge commit on `main` cannot be amended (found at the first feature
  release, 0.2.0, whose entry keeps the line). release-please keeps a
  release pull request up to date
  from the commits merged since the last tag — the next version in
  `pyproject.toml` and `__init__.py` (an `x-release-please-version`
  annotation) and the CHANGELOG entry — and merging it creates the tag and
  the GitHub release. The CHANGELOG is therefore generated, not written: a
  consumer-facing procedure goes to `docs/migrations/<topic>.md`, and only
  for a large change; small ones are followed from the commits. release-please
  runs with a token of a person or an app, so that CI runs on the release
  pull request (a pull request opened with the workflow's own token triggers
  none).
- `schema` in `mgtk-repo-utils.toml` is 1 for all of 0.x. Within 0.x a configuration
  change that is not backward compatible increments `schema` and is marked in
  CHANGELOG; from 1.0, `schema` changes only with a major release.
- New configuration keys arrive optional, with defaults equal to the previous
  behaviour; a file that uses one sets `requires`. The `[clone]` table arrives
  in 0.3.0 within schema 1, and a file that has one sets `requires = "0.3"`:
  `requires` is checked before unknown tables, so an older release stops with
  a message naming the release the file needs, where without `requires` it
  would stop on an unknown table. From mgtk-repo-utils 0.1.0 `requires` is also what stands
  between a machine's installation and a consumer's configuration (section 2),
  so a consumer sets it whenever its configuration needs a release newer than
  the ones its machines are known to hold. `name`, the table form
  of `root`, `defaults` and `sets` (section 13) arrive in 0.2.0 (revision 6),
  within schema 1; a file that uses them sets `requires = "0.2"`. A release
  before 0.2.0 rejects them with a message that names its version — `defaults`
  and `sets` as unknown keys, and a table-valued `root` with a message of its
  own, since `root` is a known key whose table form it does not allow — which
  is what `requires` spares the reader of the message. The key `all` was never released.
- A release that changes generated output (view layout, wording) is marked in
  CHANGELOG; consumers regenerate in the same commit that moves the pin.
  **Revision 5.3:** the mark is the commit's body, which release-please
  carries into the CHANGELOG entry.
- A release that adds, removes or renames a distribution, a hook id, a
  subcommand or an option lists it in CHANGELOG; a consumer follows in the
  commit that moves its pin. (Until 0.3.x this bullet listed payload files.)
  **Revision 5.3:** such a change is a `feat!:` or `fix!:` commit, which
  release-please lists under breaking changes; the consumer's steps are
  written only when they are more than the pin.
- mgtk-repo-utils 0.1.0 is the release that replaces repo-kit's copy. For a
  consumer of repo-kit 0.3.x nothing is compatible in name — the
  configuration file becomes `mgtk-repo-utils.toml`, hook ids become
  `mgtk-repo-utils-*`, recipes call the command — and everything is
  compatible in content: `schema` stays 1, the tables and keys are unchanged,
  and `requires` restarts at `"0.1"`. Generated views are unchanged. A
  consumer moves in one commit: delete the copy, rename the configuration
  file and reset `requires`, rewrite the hook configuration to the hook
  repository with a frozen `rev`, rewrite its recipes to the command, drop
  the copy's exclusions from its formatters and lints, and regenerate views
  if CHANGELOG marks them. repo-kit 0.3.x stays installable from its tag in
  the archived repository for a consumer that has not moved, and receives no
  further release unless a defect requires one.

### 13. clone and resolve: configuration

```toml
requires = "0.3"

[clone]
roots = { work = "~/src", ops = "~/src/ops" }     # destination roots, by name
urls = ["git@github.com:example/*", "git@github.com:example-org/*"]

[[clone.sources]]
name = "services"                   # optional: the name `--route` uses for this source (revision 6)
file = "registry/repos.yaml"        # relative to the repository root
entries = "teams[].services[]"      # dots and [] only
root = "ops"                        # a name in `roots`
url = "git@github.com:{repo}.git"   # `{key}` takes the entry's value of `key`
id = ""                             # key that holds the id; "" = the URL's basename
aliases = ""                        # key that holds further ids, a list; "" = none
dir = "id"                          # directory name: "id" | "url" (the URL's basename)
local = "local"                     # key that holds a declared deviation; "" = none
exclude = ["notes"]                 # ids the tools do not handle
```

`[clone]` requires `roots`, `urls` and at least one source; a source requires
`file`, `entries`, `root` and `url`. Defaults: `name = ""`, `id = ""`,
`aliases = ""`, `dir = "id"`, `local = ""`, `exclude = []`, `defaults = {}`,
`sets = {}`. Unknown keys are errors, as everywhere (section 4).

- **`name`** (revision 6) names the source on the command line (`resolve
  --route <name>`, section 14) and in reports and JSON output, where a source
  without a name is called by its position, `clone.sources[<n>]`. It matches
  `[A-Za-z0-9_-]+` and is unique among the sources (a configuration error
  otherwise). A source has no name unless it needs one: positions move when a
  source is added, so the key exists for the consumer that calls a source
  from a script.

- **`roots`** maps a name (`[A-Za-z0-9_-]+`) to a path in one of three forms:
  `~/<path>`, under the directory that `HOME` names; `/<path>`; or `$NAME`
  alone, where `NAME` matches `[A-Za-z_][A-Za-z0-9_]*` and the variable's value
  is an absolute path. Nothing else is expanded — no `${NAME}`, no variable
  inside a longer string, no relative path. A path with an empty, `.` or `..`
  component, a trailing or a repeated `/` included, or with a control
  character, is a configuration error.
  Roots may nest (`~/src` and `~/src/ops`).
- **`urls`** lists globs over the whole URL, in the syntax of
  `[links].exclude` (`*` and `?` stay within one `/`-separated segment, `**`
  spans them). It is required and must not be empty: a registry that derives
  URLs from slugs gains a stop for an unintended owner, and for a registry
  that writes a URL per entry it is the only one. Each pattern begins with
  literal text that fixes the transport and the host — `<scheme>://<host>/`,
  `[<user>@]<host>:` or `/` (a local path, as tests use) — and a pattern that
  begins otherwise, or holds `*` or `?` before that point, is a configuration
  error. Git's defaults refuse `ext::` but accept `file://` and local paths
  (`protocol.allow`); with literal prefixes, `urls` decides which of these a
  consumer accepts.

  **Correction (2026-10-11, at implementation).**
  - *Claimed:* that a literal `<host>:` before the first wildcard keeps every
    URL a pattern admits from reading as an option.
  - *Disproved by:* the implementation's tests (`tests/test_config.py` and
    `tests/test_clone.py` at 0.3.0). The pattern `--template=example:*` passes
    that rule, since its head has no `/`, `*` or `?`. A URL it admits reached
    git as `clone -- --template=example:alpha <dest>`: the `--` of section 17
    kept it an argument, and git refused the name as a host.
  - *Now holds:* neither a pattern nor its host — the part after `<user>@`, in
    either form — may begin with `-`. Such a pattern is a configuration error,
    so `--` is the second guard rather than the only one. Section 17's
    "URL as data" relies on both.
- **`file`** is a path relative to the repository root, neither absolute nor
  containing `..` (a configuration error otherwise). It is read from the
  working tree — the registry as it stands, committed or not, since a clone
  acts on the declarations in front of whoever runs it — with PyYAML's
  `yaml.safe_load`. A missing or
  unparsable file, or one whose top level is not a mapping (an empty file
  included), is a configuration error.
- **`entries`** is `segment ("." segment)*`, each segment a key
  (`[A-Za-z0-9_-]+`) optionally followed by `[]`. The walk starts at the
  document's top-level mapping; a key selects its value, and `[]` takes each
  item of a list. A key that is absent or null at any step yields no entry
  from that branch — a team without services, an empty list — and a null item
  of a list is skipped the same way. A `[]` on a value that is not a list, a
  key on a value that is not a mapping, or a final value that is neither a
  mapping nor null is a problem (section 15). Each final mapping is an entry,
  reported by its position, for example `teams[2].services[0]`. A source that
  yields no entry at all is a problem: an empty result cannot be told from a
  misspelt key, so a source that is empty on purpose leaves the configuration
  until it has entries.
- **`url`** is a template: each `{key}`, with `key` matching
  `[A-Za-z0-9_-]+`, is replaced by the entry's value of `key`, which must be a
  non-empty string. `{` and `}` appear only as placeholder delimiters; any
  other use — `{}`, `{a.b}`, an unbalanced brace — is a configuration error.
- **`id`** names the key whose string value is the entry's id. Empty, the id
  is the URL's basename, the directory name `git clone` would choose, taken in
  this order: remove trailing `/`; remove one trailing `/.git`; take the part
  after the last `/` or `:`; remove one trailing `.git`. `https://host/o/y.git/`
  gives `y` and `/srv/x/.git` gives `x`; an empty result is a problem
  (section 15, check 3).
- **`aliases`** names a key whose value is a list of non-empty strings,
  further ids of the entry; absent or null means none. An alias equal to its
  entry's id, or repeated within the entry, is a problem (section 15, check 4),
  so that implementations built on sets and on lists agree.
- **`dir`** chooses the directory name: the id (`"id"`) or the URL's basename
  (`"url"`), for a registry whose ids differ from its repository names.
- **`local`** names the key that holds a declared deviation. When present and
  not null, its value is the entry's whole destination, written `~/<path>`,
  `/<path>` or `$NAME/<path>` in the spelling of the root it lies in
  (section 15, check 6). Spaces are allowed; control characters are not.
- **`exclude`** lists ids of the source's entries that the tools do not
  handle — typically entries kept outside every root on purpose. An excluded
  id still counts for uniqueness, and the tools name it as excluded rather
  than unknown.

The ids of an entry are its id and its aliases. An id holds no whitespace or
control character and does not begin with `-`, since it is a name typed on a
command line. Every id is unique across all sources, excluded entries
included, compared exactly; `resolve` and `clone` accept any of them and
report the entry by its id.

**Keys for routed entries and selection sets (revision 6; 0.2.0).** Designed
in revision 4 as "later" and implemented in the release in which the first
consumer with such a registry adopts the tools (section 12, rollout step 13):

```toml
[[clone.sources]]                   # with roots `work` and `templates` declared
name = "projects"
file = "registry/projects.yaml"
entries = "projects[]"
root = { by = "class", map = { project = "work", template = "templates" } }
defaults = { class = "project" }
sets = { all = {}, active = { status = ["active"] }, projects = { status = ["active"], class = ["project"] } }
id = "name"
aliases = "aliases"
url = "{url}"
```

- `root` as a table: the entry's value of `by` selects the root through
  `map`; a value missing from `map` is a problem (section 15, check 10). `by`
  matches `[A-Za-z0-9_-]+`, every value of `map` is a declared root name, and
  `map` is not empty (configuration errors otherwise).
- `defaults`: values used where an entry lacks the key or holds null, read by
  `root.by`, `sets` and `--route` only; never by `id`, `aliases`, `local` or
  the URL placeholders, which describe the entry itself.
- `sets`: named selections of the source's entries. A set's condition is a
  table `key = [values]`; the entry belongs when, for every key listed, its
  value (after `defaults`) is one of the listed values. An empty condition,
  `{}`, lists no key and therefore admits every entry of the source: it is the
  natural spelling of "all of this source", not a special case. Set names
  match `[A-Za-z0-9_-]+`; a name declared by several sources denotes the
  union, in source order then entry order; a source without `sets` belongs to
  no set. `all` is an ordinary name that `--all` abbreviates (`--set all`), so
  a configuration that declares no `all` rejects `--all` as it rejects any
  undeclared set (exit 2). Excluded entries never belong to a set.
- Values in `map`, `defaults` and the conditions of `sets` are strings and
  match only string values of the entry. An entry value of another type —
  `false`, or `on`, which YAML 1.1 reads as a boolean — is a problem for
  `root.by` (check 10) and a non-match for a set.

**Correction (2026-10-11, revision 6).** Revision 4 designed a single bulk set
under the key `all`. Before it was implemented, the first consumer to need it
asked for several named selections with different cuts of one registry; `all`
became one name among them. Nothing shipped under the old key, so no
configuration changes.

**Dependency.** `registry.py` imports PyYAML inside the function that loads a
registry, so no other tool imports it, and a repository without PyYAML keeps
every other tool. When PyYAML is missing, `resolve` and `clone` exit 2 naming
the remedy: run through an environment that has it, for example
`uv run --with pyyaml python -B <copy> resolve --check`. Because `check` runs
`resolve --check` when `[clone]` is present, a repository with the table runs
`check` where PyYAML is available; elsewhere `check` reports exit 2 for that
step and still runs the other tools and `verify` (section 3; `pin` from
mgtk-repo-utils 0.1.0). A repository without the table is unaffected. **From mgtk-repo-utils 0.1.0**
(revision 5) PyYAML is a
declared dependency of `mgtk-repo-utils-clone` and is installed with it; the
missing-PyYAML path remains only for an environment that was built another
way, and the remedy it names is to reinstall the release.

### 14. resolve

```sh
mgtk-repo-utils resolve <id>
mgtk-repo-utils resolve --set <name>                       # revision 6; `--all` is `--set all`
mgtk-repo-utils resolve --route <source> <key>=<value>...  # revision 6: an entry the registry does not hold
mgtk-repo-utils resolve --destination-root <name>          # revision 6: a destination root, expanded
mgtk-repo-utils resolve --check
mgtk-repo-utils resolve ... --format json                  # revision 6: every form but --check
```

`resolve <id>` prints one line, `<id>\t<dest>\t<url>`: the entry's id, its
destination with the root expanded, and its URL. None of the three can hold a
tab or a newline (section 15, checks 2, 3 and 6). The line is the one output
not in the report format of section 3, because scripts read it; problems and
errors go to standard error. The forms are exclusive: exactly one of `<id>`,
`--set`, `--route`, `--destination-root` and `--check`; none, two, more than
one id, or an unknown or excluded id is a usage error (exit 2). An entry with a problem that
attaches to it (section 16, step 1) exits 1 and prints it.

Expansion: `~` becomes the value of `HOME`, read from the environment and
never from the password database; `$NAME` becomes the variable's value. Both
must be absolute paths without control characters — unset, empty, relative or
holding a control character is exit 2, naming the variable and the root. Only
the requested entry's root is expanded, so a machine that lacks another root's
variable still resolves this entry; `--set` expands the roots its entries use.
The destination is the expanded root without a trailing `/`, then `/<dir>`;
or the expanded deviation. Symlinks are not resolved.

`resolve` writes nothing, reads nothing outside the repository and uses no
network. It does not look at the destination: whether the root exists and what
the destination holds are `clone`'s concern.

`resolve --check` is the static check of section 15.

**`--set <name>`** (revision 6) prints one line per entry of the set (section
13), in source order then entry order. An entry with a problem that attaches
to it is printed as that problem on standard error instead of a line, and the
exit code is 1 after the whole set has been printed; an undeclared name is a
usage error. `--all` is `--set all`.

**`--route <source> <key>=<value>...`** (revision 6) answers, for an entry the
registry does not hold yet, where `clone` would place it and whether it
would be a valid declaration — for the consumer whose scripts create
repositories and want the same rule as the tool, kept in one place. `<source>`
is a source's `name` (section 13; a source without one cannot be routed), and
each `<key>=<value>` is a string field of the hypothetical entry, split at the
first `=`. The entry is built from these fields with the source's `defaults`
applied and run through the source's rules exactly as a registry entry would
be: `id` or the URL's basename, `aliases`, the `url` template, `dir`, a
string or routed `root`, and `local` when the caller gives one (then it is a
declared deviation and checked as such). The checks of section 15 that attach
to an entry apply — 2, 3, 5, 6, 7 and 10 — and so do 4 and 8 against the
registry's existing entries: an id already declared, or a destination that
equals, contains or lies inside an existing one, is a problem, since the
caller is about to add this entry. Output is the same line as `resolve
<id>`; a problem exits 1 on standard error. `--route` reads the registry to
check against it and writes nothing.

**`--destination-root <name>`** (revision 6) prints the expanded path of a
declared destination root (`clone.roots`), one line without a trailing `/`;
an undeclared name is a usage error, and an unset or malformed variable is
exit 2 as above. **Correction (2026-10-11, revision 6.1, at
implementation).** Revision 6 spelled this form `--root <name>`, which is
the common option for the repository root (section 3): the two meanings
would have shared one flag and been told apart only by the other arguments,
which section 3 keeps apart on purpose. The form is spelled by the name
section 3 gives these directories.

**`--format json`** (revision 6) replaces the line output of `<id>`, `--set`
and `--route` by one JSON array on standard output — one object per entry,
in the same order, with the fields `id`, `destination`, `url`, `root` (the
root's name), `source` (the source's name, or its position), `dir` and
`deviation` (true when the destination is a declared deviation) — and that of
`--destination-root` by one object `{"root": <name>, "path": <path>}`. Problems and usage
errors stay on standard error as text, with the same exit codes; nothing is
printed on standard output when the exit code is not 0, so a consumer that
parses the output never parses a partial array. `--check` and `clone` keep
the report format of section 3: they are read by people.

### 15. Static check (`resolve --check`)

The check reads declarations only. It expands no variable, looks up no path
and uses no network, so it gives the same answer on every machine and in CI.
Paths are compared as declared text; the forms of section 13 admit no empty
component, so nothing is normalised. Destinations are also compared after
case folding and Unicode normalisation (NFC): on a case-insensitive
filesystem, the default on macOS, `Foo` and `foo` are one directory, and the
check is stricter than a case-sensitive machine needs so that it gives one
answer everywhere.

Each problem is reported as `<file>: <entry position> (<id>): <message>`. A
problem found before the entry has an id names the position alone, and one
that belongs to the configuration rather than to an entry (check 9) is
reported against `mgtk-repo-utils.toml`. Any problem exits 1:

1. A walk error in `entries`, or a source that yields no entry (section 13).
2. An entry whose value for a placeholder or for `id` is missing or not a
   non-empty string, or whose `aliases` value is not a list of non-empty
   strings; an id, an alias or a URL that holds whitespace or a control
   character; an id or an alias that begins with `-`.
3. A directory name that is not one path component: empty, `.` or `..`,
   containing `/`, `\`, NUL or a control character, or starting with `-`.
4. An id that is not unique, an alias equal to its entry's id, or an alias
   repeated within its entry; each collision names both entries.
5. A URL that no pattern in `urls` matches, or one in git's remote-helper
   form `<transport>::<address>` (`<transport>` matching
   `[A-Za-z][A-Za-z0-9+.-]*`), whatever the patterns say. Git hands such a URL
   to a program `git-remote-<transport>`, and a pattern such as `host:*` would
   otherwise admit `host::x` (added at the code review of 2026-10-11).
6. A declared deviation in a form section 13 does not allow, with an empty,
   `.` or `..` component or a control character, or outside every root: its
   text does not begin with a root's declared text followed by `/`. A
   deviation inside a root is written in that root's spelling (`~/src/x`, not
   the expanded path); one meant to be outside every root is excluded instead.
7. A declared deviation equal to the default destination, `<root>/<dir>` as
   declared text: delete it.
8. Two destinations, default or declared, of which one equals or lies inside
   the other; or a destination that equals a root or contains one. With the
   roots of section 13's example, a `work` entry whose directory is `ops`
   defaults to `~/src/ops`, which is the `ops` root.
9. An `exclude` id that matches no entry of its source.
10. (revision 6) For a source whose `root` is a table: an entry whose value
    for `by` (after `defaults`) is missing, not a string, or not a key of
    `map`.

Excluded entries take part in 4 and 9 only, except that an entry whose id
cannot be determined is reported under 2, since nothing can match it against
`exclude`. The configuration side of revision 6 — `name` unique and
well-formed, `by` and the set names well-formed, `map` non-empty and naming
declared roots, string values throughout — is validated with the table
(section 4), so it is a configuration error (exit 2), not a problem. A missing or unreadable registry file, a parse error (with PyYAML's
line), a registry whose top level is not a mapping and a `[clone]` table that
fails validation are configuration errors (exit 2).

What the check cannot see: comparing declared text, it takes two roots for
distinct when their variables hold the same value on some machine, or when
one is reached through a symlink from another. `clone` meets those cases at
run time: containment compares resolved paths (section 16, step 3), and an
existing destination is never overwritten (step 5).

### 16. clone

```sh
mgtk-repo-utils clone <id> [--update]
mgtk-repo-utils clone --set <name> [--update]    # revision 6; `--all` is `--set all`
```

`clone` takes exactly one id or one set; none, both, more than one id, or an
unknown or excluded id or an undeclared set is a usage error (exit 2), as for
`resolve`. **`--set <name>`** (revision 6) applies the steps below to each
entry of the set in turn, in source order then entry order; a failure stops
that entry only, the next entry is still attempted, each entry's report is
printed as it finishes, and the exit code is the highest over the entries
(the rule of `check`, section 3). A missing root (step 2) is reported once per
root. For the entry that `<id>` names, in order, stopping at the first
failure:

1. **Declaration.** The entry has none of the problems of section 15 that
   attach to it: checks 2, 3, 5, 6 and 7 on the entry itself, check 4 when the
   collision involves one of its ids, and check 8 when the conflict involves its
   destination. Otherwise exit 1 with them. Problems that attach to other
   entries, walk errors elsewhere in its source (check 1) and unmatched
   excludes (check 9) do not stop it. `resolve <id>` applies the same rule.
2. **Root.** The destination root exists and is a directory; for a declared
   deviation, so does the destination's parent. Otherwise exit 2 with the
   command that creates it (`mkdir -p <path>`). Nothing is created: a missing
   root is more often a wrong variable or path than a new machine, and
   creating it would scatter clones in the wrong place.
3. **Containment.** The destination with symlinks resolved — an existing
   destination itself, a missing one through its parent — lies strictly inside
   its root, also resolved, and neither equals nor contains another root that
   expands on this machine, resolved (a root whose variable is unset is
   skipped here). For a deviation, the root is the one whose declared text it
   begins with, the longest when roots nest. Otherwise exit 1; nothing is
   written.
4. **Missing destination.** Nothing exists at the destination, by `lstat`, so
   a dangling symlink counts as existing. Run `git clone -- <url> <dest>`;
   exit 1 with git's message if it fails.
5. **Existing destination.** It must be the top of a git work tree:
   `git -C <dest> rev-parse --show-prefix` succeeds and prints an empty line.
   Comparing `--show-toplevel` with the destination would fail under a
   symlinked root, since git prints the resolved path, and success alone would
   accept a plain directory inside some enclosing work tree. Anything else — a
   file, a dangling symlink, a bare repository, a directory that is not a
   checkout — is exit 1 with nothing done, naming what was found; an empty
   directory is reported with the command that removes it (`rmdir <dest>`).
   The origin URL is read as written, with
   `git -C <dest> config --get-all remote.origin.url`, so that
   `url.<base>.insteadOf` — which a machine may use to pick a key through an
   SSH host alias — does not turn every checkout into a mismatch. It must be
   exactly one value, equal to the declared URL under the comparison below. No
   origin, several values or a different URL is exit 1, reporting what was
   found and the command a person may run (`git -C <dest> remote add origin
   <url>` or `git -C <dest> remote set-url origin <url>`): the tool never runs
   it, and with `--update` it does not pull. When the URLs agree: without
   `--update`, report the checkout as present and exit 0; with `--update`, run
   `git -C <dest> pull --ff-only --no-recurse-submodules origin` and exit 1 if
   git fails, whatever git's own exit code (a history that cannot fast-forward
   exits 128).

   **Correction (2026-10-11, at implementation).**
   - *Claimed:* that `rev-parse --show-prefix` succeeding with an empty line
     identifies the top of a work tree.
   - *Disproved by:* git 2.56.0. In a bare repository, and inside a `.git`
     directory, `git -C <dir> rev-parse --show-prefix` also exits 0 and prints
     an empty line (`tests/test_clone.py`, the bare-repository case).
   - *Now holds:* `git -C <dest> rev-parse --show-prefix --is-inside-work-tree`
     exits 0 and prints an empty line, then `true`. A follow-up
     `--is-bare-repository` tells a bare repository from a git directory in
     the report. The rest of step 5 is unchanged.

   **Correction (2026-10-11, code review before release).**
   - *Claimed:* that steps 3 and 5 keep every write of `clone` inside a root
     (section 17, "Writes").
   - *Disproved by:* a review experiment with git 2.56.0. The destination was a
     linked worktree of a repository outside the root. `clone --update`
     reported `updated` and wrote `FETCH_HEAD` into
     `<outside>/.git/worktrees/<name>/`. Fetched objects and refs would land in
     that outside repository too. The same holds for any checkout whose `.git`
     is a file pointing elsewhere.
   - *Now holds:* after the work-tree test, step 5 also asks
     `git -C <dest> rev-parse --path-format=absolute --git-dir --git-common-dir`
     (git 2.31 or later; an older git fails the call, and the checkout is
     refused). Both paths, symlinks resolved, must lie strictly inside the root;
     otherwise the result is exit 1 with nothing done, with or without
     `--update`, and the tool never moves the repository data.

`--update` names `origin` because a bare `git pull` fetches from the current
branch's upstream remote, which need not be the remote whose URL was just
checked; with `origin` named, a branch whose upstream is elsewhere fails
instead, since git will not guess a branch to merge. `--no-recurse-submodules`
keeps git from fetching submodules from URLs the tool never checked.

URL comparison: a scp-like `[user@]host:path` (no `/` before the first `:`,
git's own rule), `ssh://[user@]host[:port]/path` and
`https://[user@]host[:port]/path` reduce to the host, lowercased and without
user, and the path without one leading `/`, one trailing `/` and one trailing
`.git`. A port is kept unless it is the scheme's default (22, 443), since
another port can be another server. Two URLs are equal when their reductions
are; any other URL — a local path, `file://` — compares as text after removing
one trailing `/`. Paths keep their case: a host that ignores case in paths
yields a report that a person settles, which is safe. The SSH and HTTPS
spellings of one repository therefore agree, while a checkout left on a
renamed repository's old URL is reported.

**Correction (2026-10-11, code review before release).**
- *Claimed:* that dropping the user loses nothing.
- *Disproved by:* the review. `alice@host:repo.git` and `bob@host:repo.git`
  compared equal. On a plain SSH server they name two repositories in two home
  directories, so `--update` would pull from the other one.
- *Now holds:* the user is compared when both URLs are SSH spellings
  (scp-like or `ssh://`) and both name one. A URL without a user, or an
  `https` URL, still agrees with the SSH spelling of the same host and path.

Git's own output passes through. The tool reports in the format of section 3:
`clone: ok` with what was done (cloned, present, updated), or the problems.
Every path and URL in a command the tool prints is quoted for a POSIX shell,
and a password or token in a URL's user part is masked in every report.

`--set <name>` and `--all` (revision 6; above) handle each entry of the set
as above in the order of the sources and their entries, continue after a
failure and exit with the highest code; a present checkout is not a failure.

### 17. Authority and invariants

The tools hold no authority of their own. Each authority belongs to someone
else, and the tools only narrow what that party allows.

| Authority | Held by | What the tools do |
|---|---|---|
| Keys and tokens | the machine's environment: an SSH agent, a credential helper, a per-repository environment | never receive, read or select one; call git with the environment as it is |
| Using the tools | the consumer: a `[clone]` table | without the table, `resolve` and `clone` are errors (section 4) |
| Where to write outside the repository | the consumer: `roots` | write only strictly inside a root, after resolving symlinks |
| What to fetch | the consumer: `urls` | refuse a declared URL that no pattern matches, before git runs; `--update` fetches only from `origin`, after checking its URL, and not into submodules. What git's own configuration adds — `insteadOf`, a proxy, submodules a person updates — stays the machine's |
| Each run | whoever runs the command: a person, or an automated caller under its own permissions | one simple command per operation; no prompt of their own; nothing that steps around a sandbox |

Invariants, each fixed by a test:

- **Environment.** Git runs with the tool's environment unchanged, except for
  the git calls on a destination: `git clone`, and `rev-parse`, `config` and
  `pull` run with `-C <dest>`. Those drop the variables that
  `git rev-parse --local-env-vars` lists (git 1.7.1 and later), keeping
  `GIT_CONFIG_PARAMETERS` and `GIT_CONFIG_COUNT`, which carry configuration —
  the set git itself clears before it runs a command in a submodule
  (`sanitize_repo_env` in git's `run-command.c`). For these calls the rule
  replaces section 5's, which pins `GIT_WORK_TREE` for calls on the repository
  being checked. Inherited from a hook, the variables name the consumer's own
  repository: `GIT_DIR` makes `pull`, `rev-parse` and `config` act on it, and
  `GIT_WORK_TREE`, inherited or pinned, makes `git clone` stop, or check the
  work tree out at that path when it does not exist (git 2.56). They are
  locations and repository settings, not credentials; a variable that selects
  a key, such as `GIT_SSH_COMMAND`, passes through. The tools read from the
  environment only `HOME` for `~`, the variables that `roots` name, and the
  git variables of section 5; the list of variables to drop is asked of git.
  No option and no configuration key accepts a credential.
- **Writes.** Nothing outside a root is created, written or deleted; an
  existing directory is never overwritten or removed; `--update` is
  `pull --ff-only --no-recurse-submodules origin` and nothing else; a checkout
  whose git directory lies outside its root is refused (section 16, step 5).
- **URL as data.** The URL follows `--`, so a URL beginning with `-` cannot
  become an option. The patterns of `urls` begin with a literal transport and
  host (section 13), so they decide whether `file://` and local paths are
  accepted; git's defaults already refuse `ext::`. A path or URL in a printed
  command is quoted, so a value from a registry cannot become shell syntax for
  whoever runs the command.
- **Verbs.** `resolve` never writes and never uses the network; `clone` is the
  only tool that does either.
- **No internal paths.** Roots, variable names and URL patterns live in each
  consumer's configuration; the code names none.

Out of scope: another process on the same machine that changes the filesystem
between the containment check and `git clone` (section 16, steps 3 and 4),
and a machine whose own git configuration is hostile. The tools run as their
user on that user's machine; they guard against wrong declarations and
inherited state, not against that user.

## Configuration archetypes

Each consumer's own configuration lives in that consumer; this list only shows
that the shapes met so far are expressible.

| Archetype | read | untracked | ids | statuses | notes |
|---|---|---|---|---|---|
| Hook-regenerated tracker | tracked | warn | `\d{8}_[a-z0-9-]+`, id required | active / deferred / terminal | view rewritten by pre-commit; CI runs `--check` |
| Hand-regenerated tracker | worktree | error | same | same | no hooks; a validation recipe runs `check`; `--write` before committing; `untracked_rows = "warn"` |
| Tracker with legacy numbering | tracked | warn | `(\d{3}\|\d{8})-[a-z0-9][a-z0-9.-]*`, id absent | `in-progress`, `open` / — / `closed` | `title = "field-or-h1"`; `sections = false` with a status column and `link = "title"`; hooks only, `check` by hand; a fixed table of legacy numbers kept by hand outside the markers, without a status column |
| Template-distributed tracker | tracked | warn | `\d{8}_[a-z0-9-]+`, id required | as the template declares | `status.check = false` and empty vocabularies when the template validates its schema itself; `items_allow = [".gitkeep"]`; `empty = "nothing"`; configuration rendered from template answers; copy excluded from formatter hooks |
| Flat tracker | tracked | warn | as the repository uses | as the repository uses | `items = ""`; the view sits in `issues/README.md` above the item files |

For the clone tools (sections 13 to 17):

| Archetype | sources | id and directory | url | roots | notes |
|---|---|---|---|---|---|
| Registry of slugs by kind | one file, one source per key that holds entries (for example `teams[].lead`, `teams[].services[]`, `shared[]`) | the URL's basename for both | `git@github.com:{repo}.git` | `~/…` paths, one per kind of entry | deviations in a `local` field; entries kept outside every root on purpose are excluded; no bulk set |
| Registry of URLs with routing | one source per file | `name` with `aliases`, or `slug`; the directory is the URL's basename where slugs differ from repository names | `{url}` | `$NAME`, set per machine | `root` routed by a field with `defaults` for an absent value; named `sets` (`all`, and one per cut of the registry); `name` on each source so that the consumer's scripts can ask `--route` where a new entry goes (revision 6, 0.2.0) |

## Tests

- Reader: the conformance criterion of section 6 over anonymised copies of the
  frontmatter forms found in current trackers, plus one fixture per rejection
  rule.
- Views: byte-exact regions for each archetype; an adjacent marker pair with
  zero items passes `--check` and is unchanged by `--write`; a marker quoted in
  prose is ignored.
- Slugs: the slugger's own test vectors, and a fixture of Japanese headings
  with full-width punctuation and spaces.
- Packaging (revision 5): every distribution's version equals
  `mgtk_repo_utils.__version__` and the tag; core imports no tool, and no tool imports
  another (the imports are parsed); the hook manifest names a hook per tool
  and `mgtk-repo-utils-check`, with entries that `mgtk-repo-utils tools` resolves; the root
  installs from a clone of this repository and provides the command; each
  tool distribution installs alone from the same clone with `#subdirectory=`.
- pin: one fixture per problem and warning of section 10, under each of the
  three configuration file names, with a mirror URL in `repo:`, and with no
  configuration file.
- Listing: tracked, worktree and filesystem modes, including a temporary
  directory nested inside another work tree.
- Links: a link to a directory with and without a trailing `/`; a link to an
  untracked file under `read = "tracked"`.
- check: exit code is the maximum over the tools run; a disabled tool is not
  run; a tool that exits 2 does not stop the tools after it or `pin`.
- Resolution: each clone archetype's configuration over a fixture registry;
  entry paths through absent keys, nulls, null items and empty lists; walk
  errors; a source that yields no entry; an empty registry file; placeholders
  and malformed braces; URL basenames (`x.git`, `y.git/`, `x/.git`, a trailing
  `/`, a scp-like URL without `/`), each against the directory git chooses;
  a root variable unset for another entry's root.
- Routing and sets (revision 6): a routed root with a value present, absent
  (`defaults`), null (`defaults`) and missing from `map` (check 10); a
  non-string value for `by`; sets with an empty condition, several keys, a
  name declared by two sources, an undeclared name, `--all` without `all`;
  excluded entries absent from every set; `--set` with one entry that has a
  problem (printed, exit 1, the others still listed).
- `--route` (revision 6): an entry that resolves; one whose id collides with
  a registry entry (check 4) and one whose destination nests in an existing
  one (check 8); `local=` given and checked (6, 7); a routed root chosen by
  the given field and by `defaults`; a source without `name`; a malformed
  `key=value`; the JSON object's fields.
- `--destination-root` and `--format json` (revision 6): the expanded root;
  an unset variable (exit 2, nothing on standard output); the array for `<id>`, `--set`
  and `--route` with the same order as the lines; no standard output on a
  non-zero exit.
- Static check: one fixture per problem of section 15; excluded entries in
  collisions and unmatched excludes; destinations that differ only in case;
  nested destinations and a destination equal to a root; tabs and newlines in
  ids, URLs and deviations; the same report under an empty environment.
- Containment: a destination or a parent that escapes its root through a
  symlink; a destination equal to another root; `/` and `..` in names; a
  deviation outside every root; a missing root or parent creates nothing.
- Existing destinations: a directory that is not a git checkout; a plain
  directory inside an enclosing work tree; an empty directory, a file and a
  dangling symlink; a destination under a symlinked root; a checkout with
  another remote, also with `--update`, which must not pull; a checkout
  without `origin`; a checkout whose user configuration rewrites URLs with
  `insteadOf`, which compares equal; SSH and HTTPS spellings that compare
  equal; `--update` fast-forwards a matching checkout, fails on a diverged one,
  and fails without fetching when the branch tracks a remote other than
  `origin`.
- URLs: a URL beginning with `-` stays an argument; a URL outside `urls` is
  refused before git runs; a pattern that begins with a wildcard is a
  configuration error; shell metacharacters in a value are quoted in a printed
  command; a token in a URL is masked.
- Environment: a recorded environment shows that git calls on a destination
  receive the tool's environment minus the variables git lists, and that the
  tools read no other variable; a `GIT_DIR` or `GIT_WORK_TREE` inherited from a
  hook does not redirect a clone or a pull.
- Dependency: the suite runs with PyYAML installed, so these tests hide it (a
  `None` in `sys.modules["yaml"]`, or the copy run in a subprocess without
  it). With PyYAML hidden, `resolve` and `clone` exit 2 naming the remedy,
  `check` reports exit 2 for `resolve --check` and still runs `pin`, and
  every other tool runs. From revision 5 PyYAML is a declared dependency of
  `mgtk-repo-utils-clone` and of the root distribution (for `pin`), so the import
  test no longer restricts it; the hidden-PyYAML tests stay as the test of
  the error path.
- Clone tests use local bare repositories as URLs; no test uses the network.

## Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Configuration grows into a language to cover one consumer | Medium | Medium | Keep configuration to values; a structural difference goes back to the consumer as its own code, stamped and recorded as diverged |
| The strict reader disagrees with YAML on some input | Medium | High | Reject every ambiguous form; conformance test against PyYAML over all current trackers and adopters; rejection is the only allowed difference |
| Rejections surface on adoption | High (24 lines in one repository, 1 in the adopters, 1 already invalid) | Low | These values are truncated or unreadable today; the first `--check` lists them and quoting fixes them |
| A consumer pins a tag or a branch, or nothing (revision 5) | Medium | Medium | `pin` fails inside `check` and the `mgtk-repo-utils-check` hook; `prek update --freeze` is the documented update path |
| This repository becomes unreachable — deleted, moved, access revoked (revision 5) | Low | Medium | A fetched release keeps running from the hook runner's cache and `uv`'s (measured); a consumer that needs more declares a mirror in its own records and names it in `repo:`; nothing in the pin or the hook ids depends on the URL |
| A fresh machine or CI runner cannot fetch the repository (revision 5) | Low since the repository is public (revision 5.2) | Medium | Over `https` nothing is needed; with an SSH URL, a key in the environment as for any dependency; `GIT_TERMINAL_PROMPT=0` and BatchMode so that it fails fast, and the failure names the fetch, not a tool |
| Two pins drift — a hook `rev` and a recipe's `uvx` ref (revision 5) | Medium | Low | Recipes write no ref: they call the machine's installation or derive the ref from the hook configuration; `requires` stops an old installation |
| The workspace puts a build between a change and a consumer (revision 5) | Low | Low | `uv run mgtk-repo-utils` from a checkout runs the workspace in place; `prek try-repo <path>` runs an uncommitted checkout's hooks against a consumer |
| The hook is not installed in a clone | High | Low | CI or the validation recipe runs `check`; a hooks-only repository accepts the gap and runs `check` by hand |
| Slugs differ from GitHub's renderer | Low | Low | Port the slugger's regex; the slugger is itself an emulation, so a mismatch is reported upstream and fixed in a patch release |
| A tool is wanted outside the organisation while this repository is private | Medium | Medium | Each tool is its own distribution with core as its only internal dependency; moving one is a directory move and a pin change (alternative L); publish core and that tool before the first outside consumer |
| An internal name enters a distribution, now that no consumer's lint sees the code (revision 5) | Medium | Medium | The denylist scan moves into this repository's CI with the list supplied as a secret (section 1); the SPDX and U+00A7 tests stay |
| A clone lands outside the declared roots, or inside another root or checkout | Low | High | Containment after resolving symlinks; no destination equal to or containing a root, or nested in another; destinations compared case-folded; directory names of one component; deviations under a root's declared text; nothing created; a test for each (section 17) |
| `--update` fetches from a remote nobody checked | Low | High | `pull` names `origin` after its URL is checked and does not recurse into submodules; a test with a branch that tracks another remote |
| A printed remedy carries shell syntax from a registry | Low | Medium | Values in printed commands are quoted; ids and URLs with whitespace or control characters are problems (section 15) |
| A copy becomes a place that handles credentials | Low | High | No option or key takes one; the environment passes through; a test records what the git calls receive |
| Configuration grows to fit one registry's routing | Medium | Medium | Routing and the selection sets are values (`root.by`, `defaults`, the conditions of `sets`), implemented when the first registry that needs them adopted the tools (revision 6) |
| `check` fails where PyYAML is absent | Low from mgtk-repo-utils 0.1.0 (a declared dependency); Medium at adoption of 0.3.x | Low | Only with `[clone]`; exit 2 names the remedy; `check` still runs the other tools and `pin` |

## Rollout

1. Implement v0.1 with tests; run the conformance test of section 6 on every
   current tracker and on the template's adopters.
2. Generate each consumer's view with its own configuration and diff it
   against the committed view. Intended differences fall into these classes
   only: the marker grammar, the `blocked_by` cell format, whitespace
   collapsing in cells, the counts line wording, and quoting fixes in
   frontmatter. Each consumer lists its differences in the commit that adopts
   the copy.
3. Replace the local implementations one consumer at a time, starting with the
   repository whose implementation v0.1 grew from; the template adopts the copy
   in its next minor release and reaches its adopters through `copier update`.
   The order and status of each consumer are tracked by the consumers, not here.
4. Each consumer deletes its own script in the same commit that adds the copy.

The clone tools (revision 4):

5. Implement what a registry of slugs by kind needs — one root per source, no
   `defaults`, no `all`, no routed `root` — with the tests above, and release
   it as 0.3.0. The same release changes `check` to run past a tool that exits
   2 (section 3), moves the glob matcher into `patterns.py`, and updates the
   README, the payload README and `check`'s help text, which still say that
   nothing beyond `python3` is needed and name no clone tools. CHANGELOG lists
   the added payload files and the change to `check`.
6. The first consumer adopts it: a `[clone]` table, `resolve --check` through
   `check` in its validation recipe and CI, and a recipe that runs `clone`. Its
   review of deviation fields by eye becomes check 7.
7. The consumer with scripts of its own decides whether to replace them. If it
   does, the routed root, `defaults` and `all` are implemented in the release
   it adopts and compared with its scripts' behaviour, including the one
   difference by design: its script creates a missing root, and `clone` does
   not.

The distribution change (revision 5):

8. Restructure the code into the workspace of section 1 without changing any
   tool's behaviour, using repo-kit's repository as the workshop: core, one
   distribution per tool, the root distribution with the command, `check` and
   `pin`, the hook manifest, lockstep versions, the denylist scan in CI. The
   tests of sections 5 to 9 and 13 to 17 run unchanged against the new import
   paths; the packaging and `pin` tests are added (tests). `verify`,
   `install.sh`, the payload README and the manifest are deleted.
9. Review the tree before it leaves the workshop. A reviewer who did not
   write the code — given the whole tree and nothing else of the
   maintainer's — reads code, tests, fixtures, hook manifest, README,
   CHANGELOG and this document for what belongs to one consumer or to the
   maintainer rather than to the tool. Words are the smallest part of it: the
   review also looks for a structure the tool assumes that only the
   maintainer's repositories have and configuration cannot change (an issue
   layout, a registry shape, a directory convention, a frontmatter key); a
   workflow it presumes (a commit routine, a recipe runner, a review cadence);
   a tool or process it presumes to exist; and example values that read as
   real places. Each finding is either generalised, made a configuration
   value with a documented default, or recorded as a deliberate default in
   this document. The review's result is recorded outside this repository.
   The denylist scan in CI is the machine's share of this review, not a
   substitute for it.
10. Create `MorphometricsGroup/mgtk-repo-utils` with the reviewed tree as its
    first commit (no history; revision 5.1 above), visibility per the
    organisation's rule, and release 0.1.0. The CHANGELOG starts with that
    release and names repo-kit, its releases 0.1.0 to 0.3.0 and the archived
    repository as the earlier history; its entry lists what a consumer of
    repo-kit rewrites (section 12). Views are unchanged.
11. The first consumer moves in one commit (section 12) and runs its hooks
    and CI against the hook repository. It also runs the two checks the
    background of revision 5 did not measure — a private git URL over SSH
    from a hook with no terminal, and `#subdirectory=` against the hosted
    repository — and records the result in its own tracker.
12. The other consumers follow at their own pace, each in one commit; the
    template renders the hook configuration and `mgtk-repo-utils.toml` in the
    release that drops its copy, and its adopters follow through `copier
    update`. Until a consumer moves, its repo-kit 0.3.x copy keeps working.
    When the last has moved, repo-kit's repository is archived.

Routing, sets and read-only queries (revision 6):

13. Implement the keys of section 13 (`name`, the table form of `root`,
    `defaults`, `sets`), `resolve --set`, `--route`, `--destination-root`
    and `--format json`, and `clone --set`, with the tests above, on one feature branch
    whose commits are `feat(clone):` and `feat(resolve):`; release-please
    releases 0.2.0. The consumer that asked switches its scripts to
    `resolve`/`clone` and retires its own; the one difference by design
    stays: its scripts created a missing root, and `clone` does not.

## Open questions

- Whether `verify` should also accept a list of intentional local
  modifications (patch-style) or keep "no edits, ever".
  **Closed (2026-10-11, revision 5):** `verify` is removed with the copy.
- A lock as the pin, for a consumer that is a Python project: whether `pin`
  accepts a `repo: local` hook that runs `uv run mgtk-repo-utils` when the project's
  lock holds mgtk-repo-utils at a commit, so that such a consumer keeps its one pin
  in its lock. Designed when the first such consumer asks; until then every
  consumer pins through the hook repository (section 11).
- `[tool.mgtk-repo-utils]` in `pyproject.toml` as a second home for the
  configuration, read after `mgtk-repo-utils.toml` as ruff reads its two. No consumer
  needs it today.
- Whether `pin` should also read the hook configuration of a nested project
  under prek's workspace mode. No consumer nests today.
- Two deliberate defaults a repository cannot change (section 4): the fixed
  frontmatter key shapes (`created` required, `closed` and `blocked_by`
  typed) and the Japanese orthography of emitted text (a repository that
  writes `、。` gets mixed punctuation in its generated views). Both become
  configuration values when a repository asks; neither has yet.
- Whether a consumer that already validates its schema elsewhere should hand
  its vocabularies to mgtk-repo-utils from that single source (rendering both from one
  fragment) rather than turning mgtk-repo-utils's checks off.
- Installing from a release archive without `.git`, at the first public
  release. From revision 5 this means a package index or a wheel attached to
  a release, both outside the design (non-goals).
- To confirm at implementation: that prek keeps accepting `language: system`
  alongside pre-commit's `unsupported`.
  **Answered (2026-10-06):** two consumers ran the wiring of section 11
  unchanged under prek 0.5.5; it accepted `language: system`, regenerated a
  stale view and stopped the commit once, and failed `verify` on an edited
  copy, as pre-commit does.
- A read-only query from an entry field's value to its root, for a consumer
  whose scripts create repositories where `clone` would later place them. It
  belongs in `resolve` when such a consumer adopts the tools, so that the
  mapping keeps one home; it is not designed yet.
  **Designed (2026-10-11, revision 6):** `resolve --route <source>
  <key>=<value>...` and `resolve --destination-root <name>`, section 14.
- To confirm at implementation: that the variables dropped for git calls on a
  destination (section 17) match the set git itself clears before it runs a
  command in a submodule.
  **Answered (2026-10-11):** they do. `prepare_other_repo_env` in git's
  `run-command.c`, which `prepare_submodule_repo_env` in `submodule.c` calls,
  pushes every name of `local_repo_env` except `GIT_CONFIG_PARAMETERS` and
  `GIT_CONFIG_COUNT`, then sets `GIT_DIR` to the other repository; the tool
  uses `-C <dest>` instead of setting `GIT_DIR`. git 2.56.0 lists 15 names for
  `--local-env-vars`; `GIT_CONFIG_COUNT` joined the list in 2.31.

## Revision history

- 2026-10-11, revision 6: routed roots and selection sets, and read-only
  queries, designed for 0.2.0 at the request of the first consumer with such
  a registry (its decision to replace its own scripts came the same day).
  Section 13: `name` on a source; the table form of `root` and `defaults`
  from revision 4; `sets` of named selections in place of the single `all`
  (corrected before release; `all` is now a name `--all` abbreviates; an
  empty condition admits every entry). Section 14: `--set`, `--route` (an
  entry the registry does not hold, checked against the registry as the
  caller is about to add it), `--destination-root` (spelled `--root` until
  revision 6.1 corrected the collision with the common option), `--format
  json` (one array, nothing on standard output when the exit code is not 0). Section 15: check 10 and
  the configuration-side validation. Section 16: `clone --set` continues
  past a failing entry and exits with the highest code. Tests, section 12
  (`requires = "0.2"`), the archetype table, rollout step 13 and the open
  question follow. The decisions (an empty condition as "all of this source",
  a `name` key rather than the file as the handle, a JSON array rather than
  lines, continuing past failures) were taken with the maintainer.
- 2026-10-11, revision 5.3: dated corrections after the first adopter outside
  this repository's hook runner found that pre-commit cannot install the
  release — one distribution instead of one per tool (sections 1, 2 and 12),
  with a packaging test and a pip-install job in CI. Releases: GitHub Flow, a
  ruleset on `main`, Conventional Commits, release-please generating the
  CHANGELOG and the tag, migration pages only for large changes (section 12),
  on the maintainer's instruction.
- 2026-10-11, revision 5.2: 0.1.0 released from `MorphometricsGroup/mgtk-repo-utils`
  and the repository made public the same day, after the review of rollout
  step 9 (background of revision 5, last paragraph; section 2's
  authentication; the fetch risk). The command examples use the `https` URL.
  The first consumer moved (rollout step 11); its CI reaches the repository
  without a credential.

- 2026-10-11, revision 5.1: the tool becomes mgtk-repo-utils, governed by the
  organisation that hosts it, in a new repository that starts without
  repo-kit's history, at version 0.1.0, with the organisation's visibility
  rule (background of revision 5, last paragraph). The command, the
  configuration file, the hook ids, the distributions and the import packages
  take the new name throughout sections 1 to 4 and 10 to 12; the rest of the
  document keeps repo-kit where it speaks of the predecessor and its releases.
  Section 12 restates compatibility for a consumer that moves from repo-kit
  0.3.x. Rollout gains a review of the tree before it leaves the workshop
  (step 9: not words alone, but assumed structures, workflows and skills) and
  names the workshop, the new repository and the archive (steps 8, 10, 12).
- 2026-10-11, revision 5: the distribution changes from a copy committed into
  each consumer to one release installed from this repository. The repository
  becomes a uv workspace — a core, one distribution per tool discovered
  through an entry-point group, and a root distribution that is both the
  `repo-kit` command and a pre-commit hook repository (sections 1 to 3). A
  consumer pins by commit in its hook configuration and `pin` enforces it
  (section 10, replacing `verify`); people and `clone` run a machine
  installation with `requires` as the guard (sections 2 and 11); versions are
  lockstep (section 12). Stdlib-only is dropped as a rule. The overview, goals
  and non-goals are rewritten, with the boundary between internal and public
  drawn in configuration and environment rather than in code. Background of
  revision 5 with its measurements; alternative A re-evaluated and chosen;
  alternatives J to M; `install.sh`, `SOURCE.md`, `MANIFEST.sha256` and the
  payload constraints that came from the copy removed; risks and rollout steps
  8 to 11; the `verify` question closed and three opened. Designed for 0.4.0
  (renumbered to mgtk-repo-utils 0.1.0 by revision 5.1) and not implemented.
  The decision is recorded outside this repository, in a record that names
  the consumers; this document does not.
- 2026-10-11, revision 4.1: dated corrections from the implementation of
  0.3.0 and its code review.
  - Section 13: neither a `urls` pattern nor its host may begin with `-`.
  - Section 15: check 5 also refuses git's remote-helper form.
  - Section 16, step 5: it also asks `--is-inside-work-tree`, since
    `--show-prefix` alone is empty in a bare repository. It refuses a checkout
    whose git directory lies outside the root.
  - Section 16, URL comparison: the SSH user is compared when both URLs name
    one.
  - The status now names 0.3.0.
- 2026-10-11, revision 4: the `resolve` and `clone` tools (sections 13 to 17),
  designed for 0.3.0 and not yet implemented. The overview and goals tell the
  tools that inspect and generate from those that read registries, and
  `resolve` from `clone`;
  non-goals for preparing machines, handling credentials, repairing checkouts
  and finding undeclared clones; background and alternatives E to I; PyYAML
  imported only by the registry reader; the authority table and its invariants.
  The routed root, `defaults` and `all` are designed and left to the release
  in which a consumer adopts them. The risk of a private repository now names
  the maintainer's scan instead of CI, which revision 3.4 missed. Design
  review applied the same day, before merge — `--update` pulls only from
  `origin`, without submodules; the problems that stop `resolve <id>` and
  `clone <id>` listed; a source that yields no entry is a problem;
  destinations checked for nesting and against roots, and compared
  case-folded; the origin URL read without `insteadOf`, the work-tree top
  tested with `--show-prefix`; calls on a destination drop git's variables in
  place of section 5's pin, with the rationale corrected against git 2.56;
  printed commands quoted, and no control characters in ids, URLs and
  deviations; URL patterns begin with a literal transport and host; `file`
  stays inside the repository; root variables expanded lazily for one id;
  `check` runs past a tool that exits 2; alternative I; the submodule
  question answered.
- 2026-10-10, revision 3.5: section 5 — git calls pin the work tree when a hook
  in a linked worktree passes `GIT_DIR` without `GIT_WORK_TREE`; `verify` had
  listed the whole repository as the copy's contents there.
- 2026-10-10, revision 3.4: renamed from repo-lab to repo-kit (the package
  `repo_kit`, the configuration file `repo-kit.toml`, the recommended copy
  directory and the hook ids follow); no tool changes. Section 1 corrected:
  the denylist scan of the payload is run by the maintainer outside this
  repository, not by its CI.
- 2026-10-06, revision 3.3: the prek question answered by two consumers.
- 2026-10-06, revision 3.2: consumer feedback on v0.1.0 — `SOURCE.md` values as
  code spans; `verify` tells untracked files from files gone from disk.
- 2026-10-06, revision 3.1: two dated corrections to section 6 from the
  first conformance run (leading zeros kept; `: ` warned under unknown
  keys); the single-table `status` column may be placed through `columns`.
- 2026-10-06, revision 3: consumer feedback applied — `untracked_rows`
  separated from `untracked`; links to directories; a `check` command that
  runs every configured tool and `verify`; `link = "title"`; the keys read are
  those the configuration needs (so `closed_by` is not read by default);
  remedies named in rejection messages; alternative `--config` for one-off
  runs; hooks-only repositories allowed; uv wiring example; formatter
  exclusion in every repository holding a copy; payload file changes listed in
  CHANGELOG.
- 2026-10-06, revision 2: design review applied — byte-exact view regions;
  tracked-file copies and verify, no bytecode; reader rules restated by key
  shape with block scalars and multi-line plain scalars accepted and a
  conformance criterion that current data can meet; trailing comments only
  after closed values; ported slug algorithm; defined sort, grouping, cells,
  single-table views and per-view language; flat trackers; install guards;
  `requires`; wiring choices; no migration helper.
- 2026-10-06, revision 1: first draft.
