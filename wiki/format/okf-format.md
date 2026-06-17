---
type: Reference
title: OKF Format (v0.1)
description: OKF v0.1 in one page — a directory of Markdown concepts (YAML frontmatter
  + body) where the file path is the id and Markdown links form a knowledge graph.
---
# Overview

The Open Knowledge Format (OKF) v0.1 represents knowledge as a **directory of Markdown files** — no database, no SDK, no runtime. Each `.md` file is one *concept* (a wiki page); the file's path relative to the bundle root is its unique *concept id*; and ordinary Markdown links between files form a knowledge graph layered over the filesystem tree.

An OKF **bundle** is any directory containing one or more concept files. It is distributed as a git repository (recommended), tarball, or plain subdirectory. The bundle root declares its format version with `okf_version: "0.1"` in the root `index.md` frontmatter — the only frontmatter a root `index.md` may carry.

OKF is deliberately shallow in formal semantics and deliberately deep in operational simplicity: the bet is that the next generation of knowledge is consumed by LLMs, not SPARQL engines, so the meaning comes from the model reading the text, not from a query language baked into the format. `okf-kit` is the agent-native toolkit for this format — see [okf-kit overview](/architecture/overview.md).

# Definition

A concept file has three parts:

1. **Frontmatter** — a YAML mapping between `---` delimiters on line 1. The only required field is `type` (a non-empty string; no central registry). Recommended fields are `title`, `description`, `resource`, `tags`, `timestamp`.
2. **Body** — CommonMark/GFM Markdown. Conventional depth headings (`# Schema`, `# Examples`, `# Citations`) carry soft-semantic meaning; everything else is producer-defined.
3. **Path** — the concept id. Each segment matches `[A-Za-z0-9_][A-Za-z0-9_.-]*` (e.g. `tables/users`). Reserved filenames `index.md` and `log.md` are not concepts.

# Examples

```yaml
---
type: Table
title: Users
description: User accounts.
tags: [pii, core]
---
# Schema

| Column | Type | Description |
|---|---|---|
| id | int | Primary key |
| email | string | Unique email |

# Examples

    SELECT * FROM users LIMIT 10;
```

Cross-references use Markdown links — absolute (`[customers](/tables/customers.md)`, recommended) or relative (`[sibling](./sibling.md)`). See [Links and the graph](/format/links.md) and [Conformance](/format/conformance.md).