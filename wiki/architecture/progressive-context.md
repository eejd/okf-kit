---
type: Architecture
title: Progressive context
description: 'The load-bearing commitment — agents load the minimum and expand on
  demand under a token budget: search → read depth=0 → read depth=N.'
---
# Overview

Agents must not dump a whole bundle into context. OKF's answer is **one primitive, three depths**: `search` returns a cheap hit list (cid/title/type/snippet — no bodies); `read_concept(depth=0)` returns one concept's raw text; `read_concept(depth=1..N)` returns the seed in full plus its N-hop Markdown-linked neighborhood, concatenated and truncated to a token budget. An agent starts cheap and expands only when the answer needs more.

# Definition

`read_concept(cid, depth, token_budget)`:

- **depth=0** — the raw file (frontmatter + body), nothing else.
- **depth>0** — the seed always in full, then neighbors in deterministic **BFS** order (alphabetical tiebreak within each level), each under a `# <cid> (depth k)` header. The running char estimate (`len/4`) is bounded by `token_budget`; anything that would overflow is skipped and named in a trailing `… (N concepts omitted …)` marker.

This is the **only** context loader — there is deliberately no separate `context` tool. It is cycle-safe (BFS visits each node once), deterministic (same input → same output), and self-describing (the leading HTML comment records seed/depth/budget; the trailing marker tells the agent exactly what it is missing and how to get it).

# Examples

A reader investigating `metrics/churn` would: `search('churn')` to confirm the id, `read_concept('metrics/churn')` for the definition, then `read_concept('metrics/churn', depth=1)` to pull in the table concepts it links to. The loader is implemented in [context module](/core/context.md); the cheap hit list comes from [search module](/core/search.md).