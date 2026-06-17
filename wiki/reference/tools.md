---
type: Reference
title: Tool reference (canonical)
description: Canonical reference for the okf CLI and okf-mcp server — each tool's
  description lives in a desc:start/desc:end block asserted to match mcp.py, so docs
  and server never drift.
---
# Overview

Canonical reference for the `okf` CLI and the `okf-mcp` server. Each tool's **canonical description** — the agent trigger surface — lives in a `<!-- desc:start -->` … `<!-- desc:end -->` block below; the test suite asserts these match the strings embedded in [okf-mcp](/interfaces/okf-mcp.md), so this page and the server never drift (see [Tool doc sync](/conventions/tool-doc-sync.md)).

All commands operate on a *bundle* — a directory of OKF `.md` concept files. The five MCP tools are `search`, `read_concept` (with `depth` for [progressive context](/architecture/progressive-context.md)), `validate`, `create_concept`, and `init_bundle`; the `okf` CLI mirrors them plus `index regen` and `serve`.

## search

Full-text discovery. Ranked hits (exact title > frontmatter > body) with a snippet. Cheap: ids + snippets, no full bodies — the first step of progressive context.

- **CLI:** `okf search <bundle> <query> [--type T --tag T --limit N] [--json]`
- **MCP:** `search(bundle, query, type[]?, tag[]?, limit?) -> [{cid,title,type,snippet,score}]`

<!-- desc:start -->
Discover OKF concepts without loading full bodies. Searches title, description, body, tags, and type, then returns ranked hits with cid/title/type/snippet/score. Use this before read_concept when you do not already know the concept id, and narrow with type[] or tag[] when the bundle is large. Empty query lists concepts after filters. Example: search(bundle='analytics', query='customer churn', type=['Metric','Table']).
<!-- desc:end -->

## read_concept

Read one concept, or — with `depth>0` — its N-hop link neighborhood as concatenated Markdown under a token budget. This is the progressive-context loader.

- **CLI:** `okf read <bundle> <concept-id> [--depth N --token-budget B]`
- **MCP:** `read_concept(bundle, concept_id, depth=0, token_budget=8000) -> markdown`

<!-- desc:start -->
Read a concept by id, or progressively load its linked neighborhood. depth=0 returns only that concept's raw frontmatter plus Markdown body. depth=1..N returns the seed in full plus Markdown-linked neighbors in deterministic BFS order within token_budget; a trailing marker names omitted neighbors. Start at depth=0, then increase depth only when the answer needs surrounding context. Example: read_concept(bundle='analytics', concept_id='metrics/churn', depth=1).
<!-- desc:end -->

## validate

Check OKF v0.1 conformance (SPEC §9). Returns `{conformant, errors, warnings, info}`. Errors block conformance; warnings/info are non-blocking.

- **CLI:** `okf validate <bundle> [--json]` (exit 1 if not conformant)
- **MCP:** `validate(bundle) -> {conformant, errors, warnings, info}`

<!-- desc:start -->
Validate an OKF bundle against v0.1 conformance (SPEC §9). Returns {conformant, errors, warnings, info}. Errors such as missing frontmatter, invalid frontmatter, or empty type block conformance. Warnings such as missing title/description, invalid cids, and broken links are non-blocking. Info includes extension keys, nested sub-bundle markers, okf_version state, and empty bundles. Use after authoring and before publishing or CI. Example: validate(bundle='analytics').
<!-- desc:end -->

## create_concept

Create a concept **via MCP**. Unlike the CLI's `okf new` (a thin stub), it enforces a **richness floor**: the body must be ≥120 words and contain a depth section. This makes "created via MCP → good info" true by construction.

- **MCP:** `create_concept(bundle, cid, type, title, description, body, tags?) -> {created, cid, path}`
- Containment + atomic exclusive create are inherited from `core/templates.create_concept`.

<!-- desc:start -->
Create one substantive OKF concept. Use after searching/reading nearby concepts so the new page is specific, linked, and non-duplicative. The body must be >=120 words and include at least one depth heading: # Overview, # Definition, # Schema, # Endpoints, # API, # Steps, # Examples, or # Citations. Write concrete Markdown with relevant headings, examples, caveats, and bundle-relative links such as [Users](/tables/users.md); do not create placeholders or generic filler. Returns the created cid and path; rejects thin bodies, invalid ids, path escapes, and existing files.
<!-- desc:end -->

## init_bundle

Initialize (or re-initialize) a bundle root via MCP — writes `index.md` with `okf_version`. Idempotent.

- **MCP:** `init_bundle(bundle, okf_version='0.1') -> {initialized, path}`

<!-- desc:start -->
Initialize a registered OKF bundle root by writing root index.md with okf_version. Creates the directory if needed and rewrites index.md if it already exists, so use it before authoring a new bundle or when intentionally resetting the root index metadata. Example: init_bundle(bundle='wiki').
<!-- desc:end -->

## Build commands (CLI only)

The CLI builds thin stubs fast (`okf new`) and regenerates indexes; for rich, MCP-mediated authoring use `create_concept`. The `okf-author` skill runs the author → link → validate → index loop (see [Authoring](/guides/authoring.md)).

| Command | Purpose |
|---|---|
| `okf init <dir>` | Scaffold a bundle: root `index.md` with `okf_version`. |
| `okf new <bundle> <type> <id>` | Create a concept from a type template. |
| `okf index regen <bundle>` | Regenerate per-directory `index.md` (type-grouped). |

Exit codes: `0` success, `1` conformance errors, `2` usage / not-found / IO.