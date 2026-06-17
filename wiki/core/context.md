---
type: Module
title: core/context — progressive loader
description: read_concept and the depth-N BFS neighborhood loader — the single context
  primitive, deterministic, cycle-safe, token-budgeted.
---
# Overview

`okf_kit/core/context.py` is the progressive-context primitive (REQ-AGT-07/08, design §7). `read_concept` returns one concept at depth 0, or a depth-N Markdown-linked neighborhood at depth>0 — concatenated within a token budget. This is the **only** context loader; there is deliberately no separate `context` tool. See [Progressive context](/architecture/progressive-context.md).

# Definition

`read_concept(root, cid, depth=0, token_budget=8000)`:

- Resolves the seed via `resolve_cid_path`; a miss raises `ConceptNotFound` with search-derived "did you mean" suggestions.
- **depth=0** — the raw file text.
- **depth>0** — load all concepts, build adjacency, run `_bfs_levels` from the seed. Emit a leading comment (`seed`/`depth`/`budget`), the seed in full, then each level's neighbors (alphabetical) under `# <cid> (depth k)` headers. `_estimate = len//4` accrues against `token_budget`; overflow nodes are skipped and named in a trailing `… (N concepts omitted …)` marker.

BFS is cycle-safe (a `visited` set) and deterministic (sorted levels). The trailing marker is self-describing: it tells the caller exactly what was dropped and how to fetch it (raise depth/budget, or read each).

# API

The CLI `read` command and the MCP `read_concept` tool both call this directly (the tool clamps `depth` to 0..5 and `token_budget` to 500..50000). Adjacency comes from [links module](/core/links.md); the cheap discovery step is [search module](/core/search.md).