---
id: 20261011_design-later-marks
title: "Design: two sentences still describe the routed keys and `--all` as later"
type: task
status: closed
priority: low
created: 2026-10-11
closed: 2026-10-11
closed_by: "the sentences in sections 12 and 16 now describe 0.2.0"
labels: [design]
blocked_by: []
blocks: []
related: []
---

# Design: two sentences still describe the routed keys and `--all` as later

## Summary

Revision 6 of `docs/design.md` designed the routed `root`, `defaults`,
`sets` and `--all`, and 0.2.0 implemented them, but two sentences written
before revision 6 still say they are later.

## Context

Found while closing the 0.2.0 work. Revision 6 rewrote sections 13, 14 and
16 and the rollout, and 6.1 corrected the spelling of the root query; the
two sentences sit outside the rewritten passages.

## Problem

- Section 12 says the keys of section 13 marked as later are rejected by a
  release with a message naming its version, `defaults` and `all` as
  unknown keys and a table-valued `root` with a message of its own. From
  0.2.0 the keys are accepted; the rejection described is what releases
  before 0.2.0 do.
- Section 16 describes `--all (later)` as taking "the bulk set", checking
  every root first, and treating a present checkout as not a failure. The
  implemented `--set` and `--all` of 0.2.0 are described earlier in the
  same section; this paragraph is the pre-revision-6 sketch.

## Acceptance criteria

- [x] Section 12 describes the behaviour before and from 0.2.0.
- [x] The `--all (later)` paragraph of section 16 is removed or folded into
      the description of `--set`.

## Progress

- 2026-10-11: closed in the pull request that adds this tracker; both
  passages rewritten in its design commit.

## References

- `docs/design.md` sections 12, 13, 16; CHANGELOG 0.2.0
