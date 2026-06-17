---
type: Architecture
title: Path containment (security)
description: How every concept id and link target is confined to the bundle root —
  segment validation plus resolved-path containment, including symlink escapes, on
  both read and write paths.
---
# Overview

OKF tooling is local, but ids and links still come from arbitrary Markdown, so `okf-kit` treats path safety as a hard invariant: **no caller-supplied concept id or link target can read or write a file outside the bundle root.** This is enforced on both the read path and the write path, in defense in depth.

# Definition

Two layers, both in [links module](/core/links.md):

1. **Lexical** — every concept id is validated against the SPEC §2.2 segment regex `[A-Za-z0-9_][A-Za-z0-9_.-]*` per segment. This rejects `..`, leading `/`, and other escapes at the regex layer before any filesystem touch.
2. **Resolved-path containment** — every candidate path is `.resolve()`d and checked with `relative_to(root)`. This is the layer that catches what the regex cannot: symlink escapes, and any `..` that survived into a parent resolution.

The shared enumerator `iter_concept_files` yields only resolved, in-bundle `.md` paths and de-dupes them — so a symlinked `.md` resolving outside the bundle is never read or written through validate/search/context/index/mcp. On the **write** path, `create_concept` mirrors `resolve_cid_path`: it validates segments, then checks the *parent* of the written path is contained, then opens with `O_CREAT|O_EXCL` for an atomic exclusive create (no TOCTOU clobber of an existing concept).

# Examples

`resolve_cid_path(root, cid)` returns `None` for a malformed id, an escaping path, or a missing file — the single chokepoint used by read, search-graph, and the web router. The web UI additionally contains static paths to `static/` and never assigns `innerHTML` (a security hook blocks it). See [links module](/core/links.md) and [okf serve](/interfaces/okf-serve.md).