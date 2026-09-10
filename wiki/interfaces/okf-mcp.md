---
type: Interface
title: okf-mcp server
description: The `okf-mcp` MCP server — reviewed stable and writable preview lanes,
  progressive graph traversal, and per-concept okf:// resources.
---
# Overview

`okf-mcp` (`okf_kit/mcp.py`, FastMCP) exposes registered OKF bundles to any MCP client. Stable servers default to `--write-mode disabled --lane stable`; their tool list contains no mutators. A separate review checkout uses `--write-mode draft --lane preview --expected-write-branch <preview-branch>`. The preview branch must differ from `main` and the full branch named by `--upstream-ref`. Upstream refs use `REMOTE/BRANCH` or `refs/remotes/REMOTE/BRANCH`, where `REMOTE` is one component and `BRANCH` is the complete remaining branch path; revision expressions and raw object IDs are rejected. The server verifies the preview branch before each filesystem mutation and again before commit/push, then pushes with an explicit preview refspec. Each concept is also available as an `okf://<bundle>/concepts/<cid>.md` resource.

# Definition

Tools:

- **`search`** / **`read_concept`** / **`graph_links`** / **`validate`** — revision-bound paginated discovery, directional context, typed graph traversal, and conformance/publication checks. Search v1 returns `{"schema_version":"1","results":[Hit,...],"total":N,"next_cursor":null|string}`; each hit has `cid`, `title`, `type`, `snippet`, and numeric `score`. The temporary `legacy` response returns `[Hit,...]` and rejects cursors.
- **`list_bundles`** / **`sync_status`** — registry discovery and stable/preview revision reconciliation.
- **`create_concept`** — preview-only creation with a richness floor and server-controlled draft provenance. Caller verified/trust metadata is rejected. Containment + atomic exclusive create are delegated to [templates module](/core/templates.md).
- **`init_bundle`** — idempotent; (re)writes the root `index.md`.

A `BundleRegistry` maps registered names to resolved root paths and rejects unknown bundles with a helpful "registered: …" message. Per-concept resources are registered at startup as static no-arg readers (title/description from frontmatter).

`read_concept` returns Markdown text. `graph_links` returns
`{bundle,concept_id,direction,edges}`; each edge carries source/target OKF URIs, bundle ids,
concept ids, and `relation`. `validate` returns
`{conformant,publishable,profile,errors,publication_errors,warnings,info}`. `list_bundles` returns
`[{bundle,path},...]`. `sync_status` always returns
`{bundle,path,lane,write_mode,expected_write_branch,git_commit,tracked}`. The `git_commit` boolean
is a deprecated compatibility alias; consumers use `write_mode`. An untracked response stops
there. A tracked response always adds
`{repo,sha,served_sha,upstream_ref,upstream_sha,reconciliation,branch,detached,dirty}`. `sha` is a
deprecated alias identical to canonical `served_sha`; unavailable revisions/status values are
null. A valid detached checkout has `branch:null` and `detached:true`. MCP call failures are
protocol errors rather than CLI process exit codes.

# API

Each tool's description is the agent trigger surface and is kept verbatim in sync with the [Tool reference](/reference/tools.md) wiki concept and the CLI `--help` (a test asserts it — see [Tool doc sync](/conventions/tool-doc-sync.md)). The richness check (`_check_richness`) is the mechanism that makes "created via MCP ⇒ good info". This very wiki was built with `create_concept`. See [progressive context](/architecture/progressive-context.md) and [templates module](/core/templates.md).
