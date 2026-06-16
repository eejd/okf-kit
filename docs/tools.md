# OKF tools — reference

Canonical reference for the `okf` CLI and the `okf-mcp` server. Each tool's
**canonical description** (the agent trigger surface) lives in a
`<!-- desc:start -->` … `<!-- desc:end -->` block; the test suite asserts these
match the strings embedded in `okf_kit/mcp.py`, so the docs and the server never
drift.

All commands operate on a *bundle* — a directory of OKF `.md` concept files.

## search

Full-text discovery. Ranked hits (exact title > frontmatter > body) with a
snippet. Cheap: returns ids + snippets, no full bodies — the first step of
progressive context loading.

- **CLI:** `okf search <bundle> <query> [--type T --tag T --limit N] [--json]`
- **MCP:** `search(bundle, query, type[]?, tag[]?, limit?) -> [{cid,title,type,snippet,score}]`

<!-- desc:start -->
Full-text search across an OKF bundle over title/description/body/tags/type. Returns ranked hits (exact title > frontmatter > body) with a snippet. Use this FIRST to discover concepts — it returns only id/title/type/snippet/score (no full bodies), the cheap entry point of progressive context loading. Narrow with type[]/tag[]. Params: bundle (registered bundle name), query, type[] (optional), tag[] (optional), limit (default 20). Example: search(bundle='analytics', query='customer churn', type=['Metric','Table']).
<!-- desc:end -->

## read_concept

Read one concept, or — with `depth>0` — its N-hop link neighborhood as
concatenated Markdown under a token budget. This **is** the progressive-context
loader.

- **CLI:** `okf read <bundle> <concept-id> [--depth N --token-budget B]`
- **MCP:** `read_concept(bundle, concept_id, depth=0, token_budget=8000) -> markdown`

<!-- desc:start -->
Read one OKF concept by id (bundle-relative path without .md, e.g. 'tables/users'): returns frontmatter + Markdown body. Set depth=0 (default) for just this concept; set depth=1..N to progressively expand the N-hop neighborhood — the concept plus concepts it links to via relative Markdown links, concatenated in BFS order within token_budget (default 8000). This is the progressive-context loader: start at depth 0, raise depth only if you need surrounding context; a trailing marker names any neighbors omitted. Params: bundle, concept_id, depth, token_budget. Example: read_concept(bundle='analytics', concept_id='metrics/churn', depth=1).
<!-- desc:end -->

## validate

Check OKF v0.1 conformance (SPEC §9). Returns `{conformant, errors, warnings,
info}`. Errors block conformance; warnings/info are non-blocking. Use before
publishing or in CI (CLI exits non-zero on errors).

- **CLI:** `okf validate <bundle> [--json]` (exit 1 if not conformant)
- **MCP:** `validate(bundle) -> {conformant, errors, warnings, info}`

<!-- desc:start -->
Validate an OKF bundle against v0.1 conformance (SPEC §9). Returns {conformant, errors, warnings, info}. Errors (missing frontmatter, empty type, malformed reserved files) block conformance; warnings (missing recommended fields, broken links); info (unknown types, extension keys, nested sub-bundle markers, okf_version). Permissive — never rejects for missing optional fields/unknown types. Use before publishing or in CI. Params: bundle. Example: validate(bundle='analytics').
<!-- desc:end -->

## Build commands (CLI only)

These have no MCP tool — building is done via the CLI and the `okf-author` skill
(the agent writes `.md` files directly; OKF is just Markdown).

| Command | Purpose |
|---|---|
| `okf init <dir>` | Scaffold a bundle: root `index.md` with `okf_version`. |
| `okf new <bundle> <type> <id> [--title --desc --tag]` | Create a concept from a type template. |
| `okf index regen <bundle>` | Regenerate per-directory `index.md` (type-grouped). |

Exit codes: `0` success, `1` conformance errors, `2` usage / not-found / IO.
