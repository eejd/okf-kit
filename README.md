# okf-kit

**Build and serve [Open Knowledge Format](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) (OKF v0.1) knowledge bundles — via a CLI and an MCP server.**

An OKF bundle is a directory of Markdown files; each file is one *concept* (YAML
frontmatter + body), the file path is its id, and relative Markdown links form a
knowledge graph. `okf-kit` is an agent-native toolkit for that format: a pure
Python core exposed two ways — the **`okf` CLI** and the **`okf-mcp`** MCP server
(the universal layer for Claude Code, Antigravity, and any MCP client) — plus
**`okf-search`**, **`okf-author`**, and **`okf-code`** skills.

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

### Optional code indexing

Codebase indexing is opt-in because it pulls parser dependencies:

```bash
uv sync --extra dev --extra treesitter
# or, from an installed package:
pip install "okf-kit[treesitter]"
```

Code indexing currently supports Python, Java, Scala, Rust, Go, Kotlin, Perl,
C#, PHP, TypeScript, JavaScript, and HTML through `tree-sitter-language-pack`.
It generates normal OKF `CodeModule` concepts for documentation, code finding,
code-logic search, and syntax-grounded impact-analysis groundwork; it does not
claim complete semantic impact analysis.

### Install `okf` as a uv tool

To install or reinstall the CLI on this machine from this checkout:

```bash
uv tool install --force --editable .
```

Or install directly from GitHub:

```bash
uv tool install --force git+https://github.com/phanijapps/okf-kit.git
```

Both commands put `okf` and `okf-mcp` on uv's tool path. Verify with:

```bash
okf --help
okf agent install codex --scope project --dry-run
```

## Install agent skills

Install the OKF Agent Skills into a project-local agent configuration:

```bash
uv run okf agent install claude-code --scope project
uv run okf agent install codex --scope project
```

Project scope writes:

- Claude Code: `.claude/skills/{okf-search,okf-author,okf-code}/SKILL.md`
- Codex: `.codex/skills/{okf-search,okf-author,okf-code}/SKILL.md`

Use `--dry-run` to preview writes. Re-running the command refreshes files
previously installed by OKF; unmanaged local files are still refused. This
installs skills only: `okf-search` for read-only progressive context,
`okf-author` for create/update authoring loops, and `okf-code` for codebase
indexing/search/impact workflows. It does not install subagents, hooks, MCP
config, or plugins.

Run project-scope installs from the repository where you want the skills
available. The installer refuses to write inside an OKF bundle root or
subdirectory so agent skills do not become knowledge concepts by accident. Use
`--scope user` to install into the user-level agent skill directory instead.

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

## Index a codebase

With the `treesitter` extra installed, generate a code map from a repository
into an OKF bundle:

```bash
uv run okf code index /absolute/path/to/repo codekb
uv run okf validate codekb
uv run okf search codekb UserService
uv run okf read codekb code/pkg/service.py --depth 1
```

`okf code index` writes managed `CodeModule` concepts under `code/`, preserving
the source extension in concept ids so polyglot repositories do not collide
(`src/app.py` becomes `code/src/app.py`). By default it scans all supported
languages; repeat `--language` to limit the run, for example
`--language python --language typescript`. Re-running refreshes generated
sections while preserving hand-authored narrative outside the managed block;
`--update` is accepted for compatibility. Use the packaged `okf-code` skill for
the agent workflow: index first, then use existing `okf search` and
`okf read --depth N` over the generated concepts.

## Use it from an agent (MCP)

Start the server over stdio (it registers the bundle by its directory name):

```bash
uv run okf-mcp mykb
```

If you installed with `uv tool install`, use the tool command directly:

```bash
okf-mcp /absolute/path/to/mykb
```

For Codex, add OKF as a project-scoped MCP server from the repository where you
want Codex to use the bundle:

```bash
codex mcp add okf -- okf-mcp /absolute/path/to/mykb
```

This writes the MCP entry into Codex config. You can inspect active servers in
Codex with `/mcp` or with:

```bash
codex mcp --help
```

For Antigravity, open **Manage MCP Servers** → **View raw config** and add OKF
to the `mcpServers` object in `mcp_config.json`:

```json
{
  "mcpServers": {
    "okf": {
      "command": "okf-mcp",
      "args": ["/absolute/path/to/mykb"]
    }
  }
}
```

If you have other MCP servers, merge the `okf` entry into the existing
`mcpServers` object rather than replacing the file. See Antigravity's MCP docs:
<https://antigravity.google/docs/mcp>.

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

(If you installed `okf-mcp` onto your `PATH` via `uv tool install` or pip, the config simplifies to
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

The server exposes five tools — **`search`**, **`read_concept`** (with `depth`
for progressive context), **`validate`**, plus **`create_concept`** (enforces a
richness floor: ≥120 words + a depth section, so MCP-authored concepts are rich
by construction) and **`init_bundle`** — and an `okf://<bundle>/concepts/<id>.md`
resource per concept.

## Architecture

One pure core, two thin presentation layers (no duplicated logic):

```
okf_kit.core  (model · parse · validate · links · search · context · index · templates)
      │
      ├── okf_kit.cli   → `okf` CLI      (argparse: init/new/validate/search/read/index/code)
      └── okf_kit.mcp   → `okf-mcp`      (FastMCP/stdio: search/read_concept/validate + okf://)
```

The core is pure: deterministic, no network, no randomness. **Security:** every
caller-supplied concept id and link target is confined to the bundle root
(segment-regex validation + resolved-path containment, including symlink
escapes), on both the read and write paths. Code indexing lives outside
`okf_kit.core` and imports Tree-sitter only when `okf code index` runs.

## Status

**v0.1 — build + use a single OKF bundle.** In scope: parse/validate (SPEC §9),
search, progressive-context read, `init`/`new`/`index regen`, the MCP server,
the `okf-search`, `okf-author`, and `okf-code` skills, **`okf serve`** — a
read-only browser UI (tree, search, graph, reader) launched on demand by an
agent harness, and Tree-sitter-backed code indexing through
`okf-kit[treesitter]` for Python, Java, Scala, Rust, Go, Kotlin, Perl, C#, PHP,
TypeScript, JavaScript, and HTML.
**Next:** web-UI editing
(frontmatter form, Markdown editor, link autocomplete, CRUD) and bundle
import/export. **Later milestones (see the [`project/backlog`](wiki/project/backlog.md) wiki concept):** producer
(extract/enrich), governance (RBAC/PII/signing), and multi-bundle federation —
including the future multi-level `<domain>/<subdomain>` bundles the design
anticipates. **Git integration** is the only intentionally-deferred Phase-2 item.

## Documentation

- [`_docs/requirements.md`](_docs/requirements.md) — full OKF requirements (data model §2–4 authoritative).
- [`_docs/2026-06-16-okf-plugin-v0.1-design.md`](_docs/2026-06-16-okf-plugin-v0.1-design.md) — v0.1 design & decisions.
- [`AGENTS.md`](AGENTS.md) — build rules and structure.
- [`wiki/`](wiki/) — the OKF knowledge bundle: tool reference, progressive context, URI scheme, authoring, backlog.
- [`wiki/project/backlog.md`](wiki/project/backlog.md) — deferred findings and future work.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Gates (`ruff`, `mypy --strict`,
`pytest`) must pass; core logic is written test-first.

## License

MIT License — see [`LICENSE`](LICENSE). (The OKF format itself is a separate,
vendor-neutral spec published by Google under Apache 2.0; this project is
MIT-licensed.)
