---
type: Interface
title: okf-mcp server
description: The `okf-mcp` MCP server — five tools (search/read_concept/validate/create_concept/init_bundle),
  per-concept okf:// resources, and the create_concept richness floor.
---
# Overview

`okf-mcp` (`okf_kit/mcp.py`, FastMCP over stdio) exposes an OKF bundle to any MCP client — Claude Code, Antigravity, etc. — as **five tools** plus one `okf://<bundle>/concepts/<cid>.md` resource per concept. The bundle is registered at startup by directory name (e.g. `okf-mcp ./wiki` registers `wiki`). Tools are thin wrappers over the core; the bundle path is resolved and path-contained on every call.

# Definition

Tools:

- **`search`** / **`read_concept`** / **`validate`** — read-only, the discovery + progressive-context + conformance surface.
- **`create_concept`** — creates one concept, enforcing a **richness floor**: the body must be ≥120 words *and* contain a depth heading (`# Overview`, `# Definition`, `# Schema`, `# Endpoints`, `# API`, `# Steps`, `# Examples`, `# Citations`). Thin/generic bodies are rejected — so MCP-authored concepts are substantive by construction. Containment + atomic exclusive create are delegated to [templates module](/core/templates.md).
- **`init_bundle`** — idempotent; (re)writes the root `index.md`.

A `BundleRegistry` maps registered names to resolved root paths and rejects unknown bundles with a helpful "registered: …" message. Per-concept resources are registered at startup as static no-arg readers (title/description from frontmatter).

# API

Each tool's description is the agent trigger surface and is kept verbatim in sync with the [Tool reference](/reference/tools.md) wiki concept and the CLI `--help` (a test asserts it — see [Tool doc sync](/conventions/tool-doc-sync.md)). The richness check (`_check_richness`) is the mechanism that makes "created via MCP ⇒ good info". This very wiki was built with `create_concept`. See [progressive context](/architecture/progressive-context.md) and [templates module](/core/templates.md).