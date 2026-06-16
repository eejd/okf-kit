# okf-kit

**Build and serve [Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) (OKF v0.1) knowledge bundles — via a CLI and an MCP server.**

An OKF bundle is a directory of Markdown files; each file is one *concept* (YAML
frontmatter + body), the file path is its id, and relative Markdown links form a
knowledge graph. `okf-kit` is an agent-native toolkit for that format: a pure
Python core exposed two ways — the **`okf` CLI** and the **`okf-mcp`** MCP server
(the universal layer for Claude Code, Antigravity, and any MCP client) — plus an
**`okf-author`** skill. No web app, no REST/GraphQL.

> OKF is "what knowledge looks like once loaded" — designed for LLMs, not
> SPARQL engines. `okf-kit` makes a folder of Markdown queryable, citeable, and
> agent-addressable.

## Install

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/) (recommended).

```bash
uv sync --extra dev
```

This creates a `.venv/` and installs two console entry points — **`okf`** (CLI)
and **`okf-mcp`** (server) — into `.venv/bin/` (not your global `PATH`). Run them
with `uv run`, or activate the venv first:

```bash
uv run okf --help            # prefix with `uv run` …
source .venv/bin/activate    # …or activate once, then use `okf` / `okf-mcp` bare
```

> **No uv?** `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
> installs the same `okf` and `okf-mcp` commands.

The examples below use `uv run`; drop the prefix if you've activated the venv.

## Quick start (build a knowledge base)

```bash
uv run okf init mykb --name "My Knowledge Base"
uv run okf new mykb Table tables/users --title "Users" --desc "User accounts."
uv run okf new mykb Metric metrics/churn --title "Churn" --desc "Monthly churn, see [users](../tables/users.md)."

uv run okf validate mykb                       # SPEC §9 conformance (exit 1 if not conformant)
uv run okf search mykb churn                   # full-text search
uv run okf read mykb metrics/churn --depth 1   # progressive context: concept + neighborhood
uv run okf index regen mykb                    # regenerate per-directory index.md
```

Built-in concept types: `Table`, `Metric`, `Runbook`, `Playbook`, `API` (or any
custom value). The only required frontmatter field is `type`.

## Use it from an agent (MCP)

Start the server over stdio (it registers the bundle by its directory name):

```bash
uv run okf-mcp mykb
```

For Claude Code, add an MCP server config (`.mcp.json`). Point `uv` at this repo
and at your bundle (absolute paths):

```json
{
  "mcpServers": {
    "okf": {
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/okf", "okf-mcp", "/absolute/path/to/mykb"]
    }
  }
}
```

(If you installed `okf-mcp` onto your `PATH` via pip, the config simplifies to
`"command": "okf-mcp", "args": ["/absolute/path/to/mykb"]`.)

## Browse in a browser (`okf serve`)

On demand, launch a read-only web UI over a bundle — tree navigation, search, the
graph, and a Markdown reader with backlinks. It binds `127.0.0.1`, picks a free
port, prints the URL, and runs until you stop it (Ctrl-C). It is **not** started
by `okf-mcp`; an agent harness runs it when a human wants the visual UI.

```bash
uv run okf serve mykb
# -> okf serve: 'mykb' at http://127.0.0.1:54321  (Ctrl-C to stop)
```

Then open the printed URL. Editing (frontmatter form, Markdown editor, CRUD) is
the next milestone; this is read-only.

The server exposes three tools — **`search`**, **`read_concept`** (with
`depth` for progressive context), **`validate`** — plus an
`okf://<bundle>/concepts/<id>.md` resource per concept.

## Architecture

One pure core, two thin presentation layers (no duplicated logic):

```
okf_kit.core  (model · parse · validate · links · search · context · index · templates)
      │
      ├── okf_kit.cli   → `okf` CLI      (argparse: init/new/validate/search/read/index)
      └── okf_kit.mcp   → `okf-mcp`      (FastMCP/stdio: search/read_concept/validate + okf://)
```

The core is pure: deterministic, no network, no randomness. **Security:** every
caller-supplied concept id and link target is confined to the bundle root
(segment-regex validation + resolved-path containment, including symlink
escapes), on both the read and write paths.

## Status

**v0.1 — build + use a single OKF bundle.** In scope: parse/validate (SPEC §9),
search, progressive-context read, `init`/`new`/`index regen`, the MCP server, the
`okf-author` skill, and **`okf serve`** — a read-only browser UI (tree, search,
graph, reader) launched on demand by an agent harness. **Next:** web-UI editing
(frontmatter form, Markdown editor, link autocomplete, CRUD) and bundle
import/export. **Later milestones (see `docs/backlog.md`):** producer
(extract/enrich), governance (RBAC/PII/signing), and multi-bundle federation —
including the future multi-level `<domain>/<subdomain>` bundles the design
anticipates. **Git integration** is the only intentionally-deferred Phase-2 item.

## Documentation

- [`_docs/requirements.md`](_docs/requirements.md) — full OKF requirements (data model §2–4 authoritative).
- [`_docs/2026-06-16-okf-plugin-v0.1-design.md`](_docs/2026-06-16-okf-plugin-v0.1-design.md) — v0.1 design & decisions.
- [`AGENTS.md`](AGENTS.md) — build rules and structure.
- [`docs/`](docs/) — tool reference, progressive context, URI scheme, authoring guide.
- [`docs/backlog.md`](docs/backlog.md) — deferred findings and future work.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Gates (`ruff`, `mypy --strict`,
`pytest`) must pass; core logic is written test-first.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). OKF itself is an open,
vendor-neutral format published under the same terms.
