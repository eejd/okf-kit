---
type: Reference
title: okf:// resource scheme
description: The okf://<bundle>/concepts/<id>.md MCP resource scheme — stable per-concept
  addressing alongside the read_concept tool.
---
# Overview

The `okf-mcp` server exposes each concept as an addressable MCP **resource** under a stable URI scheme:

    okf://<bundle>/concepts/<concept-id>.md

Reading a resource returns the concept's raw Markdown (frontmatter + body); the resource's MCP `name` / `description` carry the concept's `title` / `description`. Resources are how an MCP client addresses a concept by stable handle, complementing the [read_concept](/interfaces/okf-mcp.md) tool (which also supports `depth` neighborhood expansion).

# Definition

- `<bundle>` — the registered bundle name: the directory name passed to `okf-mcp <dir>` (e.g. `wiki`).
- `<concept-id>` — the concept id, i.e. the file path relative to the bundle root without `.md` (e.g. `tables/users`). May span directories.

Bundle identifiers are **paths, not flat names** — this keeps the door open to future multi-level bundles (`<domain>/<subdomain>`) without a schema change.

# Examples

- `okf://analytics/concepts/tables/users.md`
- `okf://analytics/concepts/metrics/churn.md`

# Notes (v0.1)

- Resources are enumerated at server **startup** — a snapshot. Restart the server after authoring new concepts so they appear (a v0.1 limitation, not a template).
- The same content is available via `read_concept`, which also does [progressive context](/architecture/progressive-context.md). Prefer `read_concept` when you need context; use the resource URI for stable addressing.