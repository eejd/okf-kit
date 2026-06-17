---
type: Module
title: core/links — graph + containment
description: Link extraction/resolution, adjacency & backlinks, and the shared path-containment
  guard (segment validation + resolved-path confinement).
---
# Overview

`okf_kit/core/links.py` builds the knowledge graph and enforces path safety. It extracts Markdown link targets, resolves them (absolute against the root, relative against the source directory), normalizes to concept ids, and drops anything that escapes the root or doesn't exist. It also owns the shared safe enumerator and the containment primitives every other module reuses.

# Definition

Graph functions:

- **`extract_link_targets(body)`** — raw `.md` targets via the SPEC regex `\]\(([^)\s]+\.md)(?:#[A-Za-z0-9_-]*)?\)`; external `://` targets excluded.
- **`concept_outgoing(root, concept)`** — existing, non-reserved target cids, deduped + sorted (the forward edges).
- **`build_adjacency` / `build_backlinks`** — `cid -> sorted outgoing` over all concepts, and its reverse (REQ-CONS-13).
- **`broken_links`** — raw targets that don't resolve (tolerated; reported as warnings by [validate module](/core/validate.md)).

Containment primitives (defense in depth):

- **`cid_segments_valid`** — every segment matches `[A-Za-z0-9_][A-Za-z0-9_.-]*` (lexical reject of `..` / `/`).
- **`is_within` / `resolve_cid_path`** — resolved-path containment, the layer that catches symlink escapes; `resolve_cid_path` returns `None` for malformed/escaping/missing ids.
- **`iter_concept_files`** — the shared enumerator yielding only resolved, in-bundle, de-duped `.md` paths.

# API

These are the chokepoints: read/search/context/index/mcp/web all route ids and files through `resolve_cid_path` and `iter_concept_files`. The security rationale is in [Path containment](/architecture/path-containment.md); the format rules in [Links](/format/links.md).