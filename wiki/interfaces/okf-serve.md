---
type: Interface
title: okf serve (web UI)
description: A read-only, localhost, stdlib-only web UI over a bundle — tree, search,
  graph, and a Markdown reader with backlinks. Launched on demand, not by okf-mcp.
---
# Overview

`okf serve` (`okf_kit/web/server.py`) is a read-only browser UI over a bundle — tree navigation, search, a Cytoscape graph, and a Markdown reader with a backlinks panel. It is a stdlib-only `http.server` (no framework) reusing the exact same core calls as the CLI and MCP. It binds `127.0.0.1`, picks a free port, prints the URL, and blocks until Ctrl-C. It is **not** started by `okf-mcp`; a harness runs it when a human wants the visual UI.

# Definition

A pure `route(method, path, root) -> Response` function maps requests to core calls, testable without sockets:

- `/api/index` — concepts + distinct types/tags.
- `/api/search?q=&type=&tag=&limit=` — ranked hits.
- `/api/graph` — Cytoscape elements (nodes from concepts, edges from adjacency).
- `/api/concepts/<cid>` — concept + outgoing + backlinks (ids via `resolve_cid_path`).
- `/api/backlinks/<cid>`, `/api/validate`.
- Everything else → static assets, contained to `static/`.

The vanilla-JS SPA (`static/app.js`) renders Markdown with `marked`, sanitizes with DOMPurify, and inserts via a `setHtml()` helper (DOMParser + `replaceChildren`) — it never assigns `innerHTML`, which a security hook blocks.

# Examples

```bash
uv run okf serve mykb
```

Editing (frontmatter form, Markdown editor, CRUD) is the next milestone; today it is read-only. Security model in [Path containment](/architecture/path-containment.md); core reuse in [architecture](/architecture/overview.md).