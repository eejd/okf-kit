# Open Knowledge (okf-kit)

## Overview

`okf-kit` implements the **Open Knowledge Format (OKF v0.1)** as **agent-native tooling**, not a hosted web app. An OKF bundle is a directory of Markdown files (YAML frontmatter + body); each file is one *concept*; the file path is its id; Markdown links (relative and absolute) form a knowledge graph. See `_docs/requirements.md` for the full spec — the **data model and conformance rules (§2–4) are authoritative and unchanged**.

**Delivery vehicle (approved 2026-06-16):** a Python core library exposed two ways — an `okf` **CLI** and an `okf-mcp` **MCP server** (the universal layer for Claude Code, Antigravity, and any MCP client). No REST, no GraphQL, no hosted web wiki. A Claude Code **pack** (skills/subagents/hooks) wraps the MCP server in v0.2.

**v0.1 scope = build + use a KB:** scaffold (`okf init`), author (`okf new` + the `okf-author` skill), validate (SPEC §9), search, progressive-context read, regenerate `index.md` — shipped as a Python core + `okf` CLI + a 5-tool `okf-mcp` server + the `okf-author` skill. The full pack, single-file viewer, producer, governance, and multi-level federation are deferred — see `_docs/2026-06-16-okf-plugin-v0.1-design.md` §2/§13.

### Two design commitments (load-bearing)
- **Progressive context** — agents load the minimum and expand on demand under a token budget: `search` (cheap hit list) → `read_concept(depth=0)` (one concept) → `read_concept(depth=1..N)` (N-hop neighborhood). Design §7.
- **Tools well documented** — every tool is documented in three synced places: MCP tool `description`, CLI `--help`, and the `wiki/reference/tools.md` concept. Design §11.

## Tech Stack

- Python 3.12+
- `uv` (preferred) or a stdlib `venv`
- Runtime deps: `pyyaml`, `mcp` (official SDK, `FastMCP`, stdio). Optional: `tiktoken`.
- Dev: `pytest`, `ruff`, `mypy`

## Structure

```
okf-kit/
├── okf_kit/              # Python package (one project, two entry points)
│   ├── core/             # PURE library — model, parse, validate, links, search, context, index, templates
│   ├── cli.py            # `okf` CLI (init / new / validate / search / read / index regen / serve)
│   ├── mcp.py            # `okf-mcp` server (search/read_concept/validate + create_concept/init_bundle + okf://)
│   └── web/              # `okf serve` read-only web UI (stdlib http.server + vanilla-JS SPA)
├── tests/                # unit (core, 100%), cli (subprocess), mcp (in-memory client), fixtures/
├── skills/okf-author/    # v0.1 authoring skill (SKILL.md + template assets)
├── agents/ hooks/        # RESERVED — rest populated in v0.2 Claude Code pack
wiki/                     # the OKF knowledge bundle — dogfood docs (tools, uri-scheme, authoring, backlog)
_docs/                    # requirements.md + design doc (planning)
pyproject.toml            # project + entry points: okf, okf-mcp
```

The `core/` package is pure: deterministic, no network, no randomness. `cli` and `mcp` are thin presentation layers over the same core calls — never duplicate logic between them.

## Build Guidelines

```bash
uv sync                           # install (or: python -m venv .venv && pip install -e ".[dev]")
uv run pytest                     # tests
uv run ruff check . && uv run mypy okf_kit   # gates
uv run okf init mykb              # scaffold a new bundle
uv run okf new mykb Table tables/users --title "Users"   # create a concept from a template
uv run okf validate mykb          # validate (CI-friendly; --json)
uv run okf index regen mykb       # regenerate per-directory index.md
uv run okf-mcp                    # MCP server (stdio) — point an MCP client at it
```

- **Conformance is permissive (SPEC §9).** Never raise on missing optional fields, unknown `type`, extension keys, or broken links. The parser returns a degraded concept + a `validate` finding; `validate` is the *only* judge. Errors = missing frontmatter, empty `type`, malformed reserved files.
- **Progressive context is one primitive.** `read_concept(depth>0)` *is* the context loader — do not add a separate `context` tool. Seed concept is always full; neighbors added BFS within `token_budget`; deterministic ordering; trailing marker names omissions.
- **Authoring is CLI + skill, and MCP can create too.** Scaffold with `okf init`, create thin stubs from type templates with `okf new <bundle> <type> <path>`, then `okf validate` + `okf index regen`. The `okf-author` skill runs the author → link → validate → index loop; the agent writes `.md` files directly (OKF is just markdown). MCP additionally exposes `create_concept` — which **enforces a richness floor** (≥120 words + a depth section; rejects thin bodies) — and `init_bundle`, so MCP-mediated authoring is rich by construction.
- **Links:** extract **relative AND absolute (bundle-relative)** Markdown links as edges (SPEC §5 — absolute is the recommended form); resolve relative against the source doc's directory and absolute (`/…`) against the bundle root; normalize to concept ids (strip `.md`); drop edges to non-existent concepts silently (SPEC §5.3).
- **Web UI (okf serve):** in `web/static/*.js`, never assign to an element's `innerHTML` property (a security hook blocks it). Insert HTML via `setHtml()` (DOMParser + `replaceChildren`); render bundle Markdown with `marked` then sanitize with DOMPurify before insertion. Concept ids in routes go through `resolve_cid_path`; static paths are contained to `static/`.
- **Forward-compat for multi-level bundles** (future goal — design §14): treat the bundle id as a **path**, not a flat name; the validator reports a nested `index.md` carrying `okf_version` frontmatter as **info, not an error** (it'll be the sub-bundle marker later).
- **Tool docs stay in sync.** The canonical description for each tool lives in the `wiki/reference/tools.md` concept and is copied verbatim into the MCP `description` and CLI `--help`; a test asserts they match.
- **New code ⇒ tests first / alongside.** Core targets 100% unit coverage. Match existing style; keep `core/` pure.

## Pointers

- Design & plan: `_docs/2026-06-16-okf-plugin-v0.1-design.md`
- Full requirements: `_docs/requirements.md` (data model §2–4 authoritative)
- Docs home (the `wiki/` bundle): `wiki/reference/tools.md`, `wiki/interfaces/okf-uri-scheme.md`, `wiki/guides/authoring.md`, `wiki/project/backlog.md`
