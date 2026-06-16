# `okf serve` — Web UI Design

**Version:** 1.0 · **Date:** 2026-06-16 · **Status:** Approved (build-first, read-only v1)

A local, on-demand, read-only web UI over an OKF bundle — a thin visual layer on
the existing core. **Launch model (user constraint):** `okf serve` is a CLI
command, invoked on demand by an agent harness (Claude Code, Antigravity) when a
human wants to browse the bundle visually. It is **not** auto-started by
`okf-mcp`. It binds `127.0.0.1`, picks a free port, prints the URL, and runs
until interrupted — ephemeral, opt-in.

## Stack (minimal-deps ethos)

- **Backend:** Python stdlib `http.server` (`ThreadingHTTPServer`). No new
  dependency. A pure `route(method, path, bundle)` function is the router —
  tested without sockets.
- **Frontend:** vanilla-JS single-page app, no npm/build. Offline (no CDN):
  `marked.min.js` (Markdown) + `cytoscape.min.js` (graph) vendored locally.

## Routes (all GET; concept ids via `resolve_cid_path` → containment-safe)

| Route | Returns |
|---|---|
| `GET /` | SPA (`static/index.html`) |
| `GET /api/index` | concepts + type/tag facets |
| `GET /api/search?q=&type=&tag=&limit=` | ranked hits |
| `GET /api/concepts/<id>` | frontmatter + body + outgoing + backlinks |
| `GET /api/graph` | Cytoscape `{elements:[…]}` *(= the v0.2 "full graph tool")* |
| `GET /api/backlinks/<id>` | reverse edges |
| `GET /api/validate` | SPEC §9 report |

Static serving is contained to `static/` (path-traversal rejected, SPA fallback).

## UI

Tree sidebar (concepts grouped by top directory) · search box · reader pane
(rendered Markdown + frontmatter table + backlinks) · graph toggle (Cytoscape,
click node → open concept). Internal links navigate in-app.

## Scope

- **v1 (this build, read-only):** browse · search · graph · read · backlinks.
- **v2 (next):** editing — frontmatter form, Markdown editor, link autocomplete,
  CRUD, link-validator wiring, `okf index regen` from the UI; bundle
  import/export (`okf bundle export|import`).
- **Deferred:** git integration only.

## Layout

```
okf_kit/web/
├── __init__.py
├── server.py            # route() + serve() + make_handler()
└── static/
    ├── index.html · app.js · styles.css
    └── vendor/{marked.min.js, cytoscape.min.js}
```
`okf serve <bundle> [--host 127.0.0.1] [--port 0]` CLI subcommand.

## Security / testing

- `okf serve` binds localhost; concept ids go through `resolve_cid_path`; static
  serving contained to `static/`. No new code path handles caller input beyond
  these (already-guarded) routes.
- Tests call `route(...)` directly (no socket): index/search/concept/graph/404,
  concept path-traversal → 404, static traversal → 403.
