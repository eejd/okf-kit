---
type: Reference
title: Links and the knowledge graph
description: How Markdown links become graph edges — absolute vs relative resolution,
  broken-link tolerance, and external-link handling.
---
# Overview

A bundle is simultaneously a **tree** (the filesystem hierarchy, surfaced by `index.md`) and a **graph** (Markdown links in concept bodies). The graph is built from `[text](target.md)` links: each resolves to a concept id and becomes a directed edge. Relationship type (references, joins-with, depends-on) is conveyed by surrounding prose, not by link syntax — links are deliberately untyped.

# Definition

Two link forms are edges, resolved differently:

- **Absolute** — `[x](/tables/users.md)` (leading slash) resolves against the bundle root. This is the recommended form.
- **Relative** — `[x](./sibling.md)` or `[x](../parent.md)` resolves against the source document's directory.

Resolution rules (SPEC §5.3):

- External links containing `://` are never edges (rendered in body, not in the graph).
- A target that resolves to a **non-existent** file is dropped silently — a broken link is tolerated, not malformed; it may simply be not-yet-written knowledge.
- A target that **escapes the bundle root** (via `..`, absolute paths, or symlinks) is dropped. This is both a graph rule and a security boundary — see [Path containment](/architecture/path-containment.md).

Edges are normalized to concept ids (the `.md` suffix is stripped; `index.md` / `log.md` are never edge targets). The reverse of the adjacency map yields backlinks.

# Examples

Adjacency and backlinks are computed once from all concepts in [links module](/core/links.md); the web graph viewer and the backlinks panel both consume that map. The progressive-context reader walks adjacency in BFS order — see [Progressive context](/architecture/progressive-context.md).