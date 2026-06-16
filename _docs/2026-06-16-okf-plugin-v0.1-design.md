# OKF Plugin v0.1 — Design

**Version:** 1.0
**Date:** 2026-06-16
**Status:** Approved (brainstorm output)
**Supersedes (delivery model only):** `_docs/requirements.md` v1.1 §5–§8 web-wiki delivery.
**Scope note:** The OKF *data model and conformance rules* (requirements §2–§4) are unchanged. This design only replaces the **delivery vehicle** — a hosted web wiki → an agent-native **CLI + MCP server** — and shrinks the first milestone to the agent-readable core.

---

## 1. Context & Decision Summary

`requirements.md` (v1.1) specifies a hosted web wiki (React/Vue, Cytoscape.js, marked.js, dev server, REST + GraphQL, ~239 tests, 4 phases). Two user decisions reframe it:

1. **Form factor** → Agent-native, not a web app. Build a Python **core library** exposed as an **MCP server** (universal layer: Claude Code, Antigravity, any MCP client) + an `okf` **CLI**, later wrapped by a Claude Code **pack** (skills/subagents/hooks). Drop the hosted wiki, dev server, React/Cytoscape app, and all REST/GraphQL.
2. **MVP scope** → Build-first minimal slice. v0.1 = core lib + CLI + a 3-tool MCP server + the `okf-author` skill — enough to **build and use** a KB: scaffold (`init`), author (`new` + skill), validate, search, read with context, regenerate `index.md`. Defer the full pack (more skills/subagents/hooks/commands + viewer), single-file viewer, full `graph` tool, producer, governance, and multi-bundle federation to v0.2+.

Two conditions attached to approval, both made first-class below: **progressive context loading** (§7) and **tools well documented** (§11).

---

## 2. Goals & Non-Goals

### v0.1 Goals
- OKF v0.1 conformance: parse, round-trip, and **validate** bundles per SPEC §9.
- **Search** (full-text, ranked) over title/description/body/tags/type.
- **Progressive context loading**: read one concept, then expand its N-hop link neighborhood within a token budget.
- **Build a KB**: `okf init` (scaffold a bundle), `okf new <type>` (create a concept from a per-type template), `okf index regen` (auto-generate `index.md`), and an **`okf-author`** skill running the author → link → validate → index loop.
- Expose reading/search/validate as a **CLI** (`okf`) and an **MCP server** (`okf-mcp`, 3 tools + `okf://` resources), thoroughly documented.

### Non-Goals (deferred — see §13)
- The **full** Claude Code pack (additional skills/subagents/hooks/commands, marketplace packaging) — v0.1 ships only the `okf-author` skill.
- Single-file HTML viewer; full `graph` tool / Cytoscape export; backlinks panel.
- Producer (extract/enrich + source adapters); custom type registry (`types.yaml`).
- Governance (RBAC, PII, signing); multi-bundle federation; query DSL; semantic search.
- Hosted web wiki, REST, GraphQL (removed entirely, not deferred).

---

## 3. Architecture

One Python project, two entry points, one shared core.

```
                ┌──────────────────────────────────────┐
                │            okf_kit.core               │
                │  model · parse · validate · links     │
                │  search · context                     │
                └───────────────┬──────────────────────┘
                                │ (pure library, no I/O policy)
                ┌───────────────┴──────────────────────┐
                │                                       │
        ┌───────▼────────┐                    ┌─────────▼────────┐
        │  okf_kit.cli   │                    │  okf_kit.mcp     │
        │  `okf` CLI     │                    │  `okf-mcp` server│
        │  (argparse)    │                    │  (FastMCP/stdio) │
        └────────────────┘                    └──────────────────┘
```

`core` is pure: deterministic, no network, no randomness (safe for resume/caching). `cli` and `mcp` are thin presentation layers over the same calls.

---

## 4. Package Layout

```
okf-kit/
├── okf_kit/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── model.py      # Concept, Frontmatter, Bundle dataclasses
│   │   ├── parse.py      # line-1 --- split; yaml.safe_load; graceful fallback
│   │   ├── validate.py   # SPEC §9 → Report{errors,warnings,info}
│   │   ├── links.py      # extract + resolve relative .md links → concept IDs
│   │   ├── search.py     # inverted index + ranking (title>frontmatter>body)
│   │   ├── context.py    # BFS neighborhood walk within token budget
│   │   ├── index.py      # regenerate_indexes() — per-dir index.md (type-grouped)
│   │   └── templates.py  # per-type concept templates (Table/Metric/Runbook/…/generic)
│   ├── cli.py            # `okf` entry point
│   └── mcp.py            # `okf-mcp` entry point (FastMCP, stdio)
├── tests/
│   ├── unit/             # core: 100% coverage target (parse/validate/links/search/context)
│   ├── cli/              # subprocess tests for the `okf` CLI
│   ├── mcp/              # in-memory MCP client tests
│   └── fixtures/bundles/ # 3 tiny synthetic bundles (tree / graph-linked / malformed)
├── skills/okf-author/    # v0.1: authoring skill; other skills → v0.2 pack
├── agents/               # reserved — populated in v0.2 pack
└── hooks/                # reserved — populated in v0.2 pack

docs/                     # created in v0.1 (tool reference, progressive context, URI scheme)
pyproject.toml            # root: project + entry points (okf, okf-mcp)
```

`pyproject.toml` defines: package `okf_kit`, scripts `okf = "okf_kit.cli:main"` and `okf-mcp = "okf_kit.mcp:main"`, Python ≥3.12, deps `pyyaml`, `mcp`; dev deps `pytest`, `ruff`/`mypy`.

---

## 5. Core API Contract (load-bearing)

```python
# parse.py
@dataclass
class Concept:
    cid: str                 # concept id: path rel to bundle root, no .md
    path: Path
    frontmatter: dict        # ALL keys preserved (incl. unknown/extension)
    body: str                # raw markdown, no frontmatter
    reserved: str | None     # 'index' | 'log' | None

def parse_concept(path: Path, root: Path) -> Concept            # REQ-CONS-01..04
def serialize_concept(concept: Concept) -> str                  # round-trip; preserves keys

# validate.py
@dataclass
class Report:
    conformant: bool
    errors: list[Finding]; warnings: list[Finding]; info: list[Finding]
def validate_bundle(root: Path) -> Report                       # SPEC §9; REQ-BM-04

# search.py
@dataclass
class Hit:
    cid: str; title: str; type: str; snippet: str; score: float
def build_index(root: Path) -> Index
def search(index: Index, q: str, type=None, tag=None, limit=20) -> list[Hit]   # REQ-CONS-14..17

# context.py
def read_concept(root: Path, cid: str, depth: int = 0,
                 token_budget: int = 8000) -> str                # REQ-AGT-07/08

# index.py + templates.py  (build)
def init_bundle(root: Path, okf_version: str = "0.1") -> Path           # scaffold root index.md
def create_concept(root: Path, cid: str, type: str, **fields) -> Path   # from type template (REQ-ED-05/PROD-08)
def regenerate_indexes(root: Path) -> list[Path]                        # per-dir index.md (REQ-BM-05/PROD-05)
```

---

## 6. Conformance & Validation (SPEC §9)

A bundle is conformant **iff** every non-reserved `.md` has parseable frontmatter with a non-empty `type`, and every `index.md`/`log.md` follows §6/§7 structure when present.

`validate_bundle` classifies findings:
- **Errors (blocking):** missing/unparseable frontmatter; empty/missing `type`; malformed reserved files.
- **Warnings:** missing recommended fields (`title`/`description`/…); broken internal links.
- **Info:** unknown `type` values; extension keys; missing `index.md`; missing/mismatched `okf_version`.

Consumer is **permissive** (SPEC §9): never raise on missing optional fields, unknown types, extension keys, or broken links. The parser returns a degraded `Concept` and feeds `validate` a finding instead of throwing. `validate` is the *only* judge.

---

## 7. Progressive Context Loading *(approval condition)*

The agent loads the minimum it needs and expands on demand, always under a token budget. This is OKF's own progressive-disclosure principle (index → concept → links) applied to the **LLM context window** instead of a UI pane.

**Funnel (cheap → expensive):**
1. `search` → hit list only: `cid, title, type, snippet, score`. Cheap; no bodies.
2. `read_concept(cid, depth=0)` → one full concept (frontmatter + body).
3. `read_concept(cid, depth=1..N)` → concept + N-hop neighborhood (concepts reachable via relative links), concatenated markdown.

**Token-budget semantics:**
- Every context-returning tool takes `token_budget` (default 8000).
- The **seed concept is always included in full**; neighbors are added in BFS order by depth until the budget is reached.
- On truncation, a trailing marker lists what was omitted and how to get it:
  `… (3 neighbors at depth 1 omitted: metrics/arr, tables/orders, refs/x — raise depth/token_budget or read_concept each).`
- **Deterministic:** BFS then alphabetical `cid` tiebreak; char-based token estimate (≈4 chars/token; optional `tiktoken`); no `Date`/`random`. Reproducible across runs.

**Why it matters:** the same primitive serves a quick lookup (depth 0) and a deep gather (depth 2) without a separate tool — see §8.

---

## 8. MCP Surface (v0.1 = 3 tools + resources)

Transport: **stdio**. Resources: `okf://<bundle>/concepts/<path>.md` → frontmatter as metadata, markdown body as text (REQ-AGT-01/02). Tool descriptions are the agent trigger surface — written to be self-sufficient for an MCP client (full text in §11).

| Tool | Signature | Maps to |
|---|---|---|
| `search` | `(bundle, query, type[]?, tag[]?, limit?)` → `Hit[]` | REQ-CONS-14..17 |
| `read_concept` | `(bundle, concept_id, depth=0, token_budget=8000)` → markdown str | REQ-AGT-02/07/08 |
| `validate` | `(bundle)` → `{conformant, errors, warnings, info}` | REQ-API-01..04 |

`context` is **not** a 4th tool — it is `read_concept(depth>0)`. One primitive, two behaviors.

**Building is CLI + skill, not MCP.** The server stays read+validate (which already *supports* authoring: `search` finds link targets, `validate` checks what you wrote). Scaffolding/creation/indexing happen via the `okf` CLI (`init` / `new` / `index regen`) and the `okf-author` skill — the agent writes `.md` files directly with its own file tools, the most OKF-idiomatic path. MCP write tools are deferred.

---

## 9. CLI Surface

```
okf init     <dir> [--name N]                          # scaffold a bundle: root index.md with okf_version
okf new      <bundle> <type> <path> [--title T --desc D]   # create a concept from a type template
okf validate <bundle> [--json]                         # exit non-zero on errors (CI-friendly)
okf search   <bundle> <query> [--type T] [--tag T] [--limit N] [--json]
okf read     <bundle> <concept-id> [--depth N] [--token-budget B] [--json]
okf index    regen <bundle>                            # regenerate per-directory index.md files
```
`--json` emits machine-readable output with documented schemas (§11). `validate` without `--json` prints a human-readable report; `search` prints a ranked table; `read` prints markdown.

### Authoring workflow (`okf-author` skill)
The `okf-author` skill (`okf-kit/skills/okf-author/SKILL.md`) is the agent-facing entry point for **building** a KB. It teaches the OKF format and runs the loop:
1. **Scope** — decide the concept's `type` and path (pick a known type or invent one).
2. **Scaffold** — `okf new <bundle> <type> <path>` writes a correctly-frontmatter'd stub from the type template.
3. **Author** — fill the body (`# Schema` / `# Examples` / `# Citations` conventions where relevant); add **relative** links to existing concepts (use `okf search` to find link targets).
4. **Validate** — `okf validate` → fix any errors (empty `type`, malformed frontmatter).
5. **Index** — `okf index regen` updates per-directory `index.md`.
Built-in templates (Table, Metric, Runbook, Playbook, API, …) with a generic fallback; unknown types use the generic template and are tolerated.

---

## 10. Error Handling

- Parser never raises on malformed files → degraded `Concept` + `validate` finding.
- Unknown `type`, extension keys, broken links, missing `index.md` → tolerated (info/warning), never fatal.
- Non-mapping YAML frontmatter → error finding (REQ-CONS-03).
- `read_concept` on a missing `cid` → clear "not found" error listing the nearest matches (cheap `search` fallback).
- CLI maps core errors to exit codes: `0` ok, `1` conformance errors, `2` usage/IO.

---

## 11. Tool Documentation *(approval condition)*

Every tool is documented in **three synced places**:

1. **MCP tool `description`** (in `mcp.py`) — the agent trigger surface. For each tool: what it does, when to use it, every parameter (type, required, meaning, example), return shape, and one example call. Drafts:
   - **search** — "Full-text search across an OKF bundle over title/description/body/tags/type. Returns ranked hits (exact title > frontmatter > body) with a highlighted snippet. **Use this first** to discover concepts — it's cheap (ids+snippets, no full bodies) and is the entry point of progressive context loading. Narrow with `type[]`/`tag[]`. Ex: `search(bundle='analytics', query='customer churn', type=['Metric','Table'], limit=10)`."
   - **read_concept** — "Read one concept by id (bundle-relative path, no `.md`, e.g. `tables/users`): frontmatter as metadata + markdown body. `depth=0` (default) returns just this concept; `depth=1..N` progressively expands the N-hop neighborhood (concepts linked via relative markdown links), concatenated in BFS order within `token_budget` (default 8000). This **is** the progressive-context loader — start at 0, raise depth only if you need surrounding context; a trailing marker names anything omitted. Also addressable as resource `okf://<bundle>/concepts/<path>.md`. Ex: `read_concept(bundle='analytics', concept_id='metrics/churn', depth=1, token_budget=6000)`."
   - **validate** — "Validate a bundle against OKF v0.1 conformance (SPEC §9). Returns `{conformant, errors, warnings, info}`. Errors block (missing frontmatter, empty type, malformed reserved files); warnings (missing recommended fields, broken links); info (unknown types, extension keys). Permissive — never rejects for missing optional fields/unknown types. Use before publishing or in CI. Ex: `validate(bundle='analytics')`."
2. **CLI `--help`** (argparse) — mirrors the MCP tool; documents `--json` output schema.
3. **`docs/`** — human-facing reference:
   - `docs/tools.md` — one section per tool (CLI + MCP): purpose, signature, parameter table, return schema, 2–3 worked examples against a sample bundle.
   - `docs/progressive-context.md` — the loading model from §7, with a worked depth-0→1→2 walkthrough.
   - `docs/okf-uri-scheme.md` — the `okf://` resource scheme.
   - `docs/authoring.md` — the build workflow, built-in type templates, and the author → validate → index loop.

A single source-of-truth table (tool → description) is kept in `docs/tools.md` and copied into `mcp.py` descriptions + argparse help; the test suite asserts the three stay in sync (description strings match).

---

## 12. Testing

Core-first, 100% unit (Appendix C: Parser/Conformance, Search, Link Rewriting). Fixtures: three tiny synthetic bundles covering the GA4 / StackOverflow / Bitcoin **topology patterns** (single wide table; many independent entities; tightly cross-linked facts) **plus** a malformed-edge-case bundle. CLI via `subprocess`; MCP via the SDK in-memory client. No web/e2e in v0.1. Gates: `ruff`, `mypy`, `pytest`.

---

## 13. Deferred Backlog (v0.2+)

| Milestone | Items |
|---|---|
| **v0.2 — Pack + view** | Full Claude Code pack (additional skills: `okf-explore`, `okf-validate`; subagents: `okf-curator`; hooks: pre-commit `okf validate`; commands; marketplace packaging); single-file HTML viewer; full `graph` tool + Cytoscape JSON + backlinks. |
| **v0.3 — Produce** | `extract` + `enrich` producer with ≥1 source adapter (dbt manifest / SQL schema / BigQuery); templates; provenance in `log.md`. |
| **v0.4 — Govern & federate** | RBAC, PII scan, cosign signing/verify, audit log; multi-bundle registry, cross-bundle links, federated search/graph; query DSL; semantic (vector) search; **hierarchical/nested bundles** (`<domain>/<subdomain>`). |

---

## 14. Forward-compatibility: Multi-Level Bundles (Future Goal)

Future goal: a **domain OKF containing subdomain OKFs** — `<domain>/<subdomain>` hierarchical bundles (a domain KB partitioned into subdomain KBs). This is federation (requirements §5.8, Phase 3) and is **not** in v0.1. OKF v0.1 doesn't define nesting or federation (spec gap L7), so a sub-bundle boundary is a convention added at federation time. Three hooks are baked into v0.1 to avoid rework:

1. **Bundle id is a path, not a flat name.** The `okf://<bundle>/concepts/<path>` URI and MCP `bundle` parameter accept a path, so `domain/finance` is just a deeper path later — nesting needs no schema change.
2. **Core is single-root but bundle-agnostic.** `core/` operates on one root; no global concept-id registry or "only one bundle" assumptions. A future workspace layer enumerates nested roots and federates search/graph.
3. **Validator does not hard-error on a future sub-bundle marker.** Only the bundle-root `index.md` may carry frontmatter today (§2.1); a nested `index.md` declaring `okf_version` is the likely sub-bundle marker, so the v0.1 validator reports it as **info, not an error**.

This connects to the build-first direction: start flat in v0.1, partition into subdomains as the KB grows.

---

## 15. Assumptions & Open Questions

- **MCP SDK:** official `mcp` Python SDK with `FastMCP`, stdio. Verify exact API in the implementation plan.
- **Marketplaces:** primary = Claude Code marketplace (pack, v0.2); the MCP server is the universal layer that also serves Antigravity / generic MCP clients. Antigravity-specific plugin format, if any, is a later investigation.
- **Git:** repo is not currently a git repo; versioning (REQ-VER, auto-commit) is deferred with the producer/editor work.
- **Token counting:** char-based default; `tiktoken` optional dependency. Confirm acceptable in planning.
- **Multi-level bundles:** sub-bundle marker convention (nested `index.md` with `okf_version` vs. `.okf/` sidecar) is deferred to the federation milestone — see §14.

---

## 16. References

- `_docs/requirements.md` v1.1 — full OKF requirements (data model §2–4 unchanged).
- OKF SPEC.md §9 — conformance rules.
- GCP blog — "How the Open Knowledge Format can improve data sharing."
- Reference impl — `GoogleCloudPlatform/knowledge-catalog/okf/`.
