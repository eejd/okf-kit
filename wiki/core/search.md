---
type: Module
title: core/search — full-text ranking
description: A dependency-free inverted index with weighted ranking (title > tag >
  type > description > body) and type/tag filters; deterministic order.
---
# Overview

`okf_kit/core/search.py` is full-text search over a bundle (REQ-CONS-14..17, REQ-SRCH-01..04) with **no external dependencies**. It builds a lightweight per-field inverted index over non-reserved concepts and ranks with field weights, returning a deterministic order (score desc, then cid asc). A future BM25/IDF ranker can swap in behind the same `search` signature.

# Definition

- **`build_index(root)`** — for each concept, tokenize (`[a-z0-9]+`) the title, tags, type, description, and body into separate `Counter`s. Reserved files are excluded.
- **`search(index, q, type=None, tag=None, limit=20)`** — rank every doc, optionally filtered by exact `type` / `tag` sets. An empty `q` returns all concepts (post-filter) by cid.

Ranking (`_score`):

- An **exact title match** adds a large boost (`_EXACT_TITLE_BOOST = 100`).
- Each query term contributes a weighted term-frequency sum: title×5, tag×4, type×3, description×2, body×1.

A hit is a `Hit(cid, title, type, snippet, score)`; the snippet centers on the first matched term with `…` ellipses.

# API

This is the cheap first step of [Progressive context](/architecture/progressive-context.md) — the hit list an agent reads before [context module](/core/context.md) loads bodies. The web search endpoint and the MCP `search` tool both call it. Filters populate from distinct `type` / `tag` values across the bundle.