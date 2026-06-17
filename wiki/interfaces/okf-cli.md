---
type: Interface
title: okf CLI
description: 'The `okf` CLI — a thin argparse layer over the core: init / new / validate
  / search / read / index / serve.'
---
# Overview

The `okf` command-line interface (`okf_kit/cli.py`) is a thin presentation layer over [the core](/architecture/overview.md). It scaffolds bundles, creates concepts, validates, searches, reads (with progressive context), regenerates indexes, and serves the web UI. There is no business logic here — each subcommand parses args and calls one core function.

# Definition

Subcommands:

- **`init <dir>`** — scaffold a bundle root (`--okf-version`, `--name`).
- **`new <bundle> <type> <path>`** — create a concept from a type template (`--title`, `--desc`, `--tag` repeatable).
- **`validate <bundle>`** — SPEC §9 conformance; `--json` for a machine report. Exit 1 on errors, 0 otherwise.
- **`search <bundle> <query>`** — full-text search; `--type` / `--tag` filters, `--limit`, `--json`.
- **`read <bundle> <concept_id>`** — read a concept; `--depth` for the neighborhood, `--token-budget`.
- **`index regen <bundle>`** — regenerate per-directory `index.md` files.
- **`serve <bundle>`** — launch the read-only web UI (`--host`, `--port`).

Exit codes: `0` success, `1` conformance errors, `2` usage / not-found / IO errors. `ConceptNotFound` prints a "did you mean" hint.

# Examples

```bash
uv run okf init mykb --name "My KB"
uv run okf new mykb Table tables/users --title "Users" --desc "User accounts."
uv run okf validate mykb
uv run okf read mykb tables/users --depth 1
uv run okf index regen mykb
```

The MCP server exposes the same core as agent tools — see [okf-mcp](/interfaces/okf-mcp.md); the browser UI is [okf serve](/interfaces/okf-serve.md). Tool docs stay in sync across `--help`, MCP descriptions, and the `reference/tools` wiki concept — see [Tool doc sync](/conventions/tool-doc-sync.md).