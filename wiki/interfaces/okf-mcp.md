---
type: Interface
title: okf-mcp server
description: The `okf-mcp` MCP server — reviewed stable and writable preview lanes,
  progressive graph traversal, and per-concept okf:// resources.
---
# Overview

`okf-mcp` (`okf_kit/mcp.py`, FastMCP) exposes registered OKF bundles to any MCP client. Stable servers default to `--write-mode disabled --lane stable`; their tool list contains no mutators. A separate review checkout uses `--write-mode draft --lane preview --expected-write-branch <branch>`. The server verifies that branch before each filesystem mutation and again before commit/push. Each concept is also available as an `okf://<bundle>/concepts/<cid>.md` resource.

# Definition

Tools:

- **`search`** / **`read_concept`** / **`graph_links`** / **`validate`** — revision-bound paginated discovery, directional context, typed graph traversal, and conformance/publication checks. Search has a temporary `legacy` response version for pre-0.3 list consumers.
- **`list_bundles`** / **`sync_status`** — registry discovery and stable/preview revision reconciliation.
- **`create_concept`** — preview-only creation with a richness floor and server-controlled draft provenance. Caller verified/trust metadata is rejected. Containment + atomic exclusive create are delegated to [templates module](/core/templates.md).
- **`init_bundle`** — idempotent; (re)writes the root `index.md`.

A `BundleRegistry` maps registered names to resolved root paths and rejects unknown bundles with a helpful "registered: …" message. Per-concept resources are registered at startup as static no-arg readers (title/description from frontmatter).

# API

Each tool's description is the agent trigger surface and is kept verbatim in sync with the [Tool reference](/reference/tools.md) wiki concept and the CLI `--help` (a test asserts it — see [Tool doc sync](/conventions/tool-doc-sync.md)). The richness check (`_check_richness`) is the mechanism that makes "created via MCP ⇒ good info". This very wiki was built with `create_concept`. See [progressive context](/architecture/progressive-context.md) and [templates module](/core/templates.md).
