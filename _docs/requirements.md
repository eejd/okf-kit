# OKF Wiki Implementation Requirements

**Version:** 1.1  
**Date:** 2026-06-17  
**Status:** Revised Draft  
**Classification:** Requirements Specification  

---

## 1. Executive Summary

The Open Knowledge Format (OKF) v0.1, published by Google Cloud on 12 June 2026, is an open, vendor-neutral specification for representing knowledge as a **directory of Markdown files with YAML frontmatter**. Each file represents one **concept** (a wiki page), and the file path serves as the concept's unique identifier. Cross-references between concepts use standard Markdown links, creating a knowledge graph atop the filesystem tree.

This document specifies the requirements for building a **general-purpose wiki system** that uses OKF as its **native storage and rendering backend**. The wiki does not import/export OKF — it *is* an OKF bundle editor and viewer. Every wiki page is an OKF concept file; every navigation action traverses the OKF bundle structure; every search queries the OKF frontmatter and body content.

> **Strategic framing.** OKF v0.1 is *the format an LLM-native organization would invent from first principles*. Its strengths — Markdown-in-git, no SDK, no runtime, human- and agent-readable, vendor-neutral — and its weaknesses — no query language, no access control, v0.1 maturity — are the predictable trade-offs of a deliberately minimal v0.1. The decisive question is not *"is OKF better than Collibra?"* but *"is OKF the right substrate for a digital brain whose primary reader is an LLM?"* The answer, as of 2026, is yes. *(Research 03 §7.4)*

### 1.1 Data-Sharing Vision

OKF was designed to unlock four knowledge-sharing scenarios that today require bespoke point-to-point integration. The wiki system is the consumer that makes these operational. *(Research 01 §6)*

| Scenario | What OKF Unlocks | Wiki Role |
|----------|------------------|-----------|
| **Agent ↔ Agent** (intra-org) | Agents share the meaning of a column, definition of a metric, or runbook for an incident — without each re-discovering and drifting. | Shared context surface agents query via MCP. |
| **Org ↔ Org** (extra-org) | Data provider ships context about a public dataset alongside the data; any OKF-aware agent ingests it. *(GA4, Stack Overflow, Bitcoin samples.)* | Imports/renders externally-provided bundles. |
| **Tool ↔ Tool** (catalog portability) | Team migrating Collibra → Unity Catalog carries their knowledge bundle — decoupled from any catalog's internal schema. | Neutral viewer over any catalog-sourced bundle. |
| **Human ↔ Agent** (same file) | The same `.md` file is human documentation, `docs/` site content, in-repo wiki, *and* agent context. No "agent view" to keep in sync. | Renders and edits that single source of truth. |

> **No vendor lock-in.** OKF's Apache 2.0 license and anti-platform stance are the commercial point: the format is a public good; the value to Google is adoption. The play mirrors Kubernetes (CNCF + GKE), TensorFlow, and gRPC. *(Research 01 §6.5)*

### Key Design Principles

| Principle | Description |
|-----------|-------------|
| **OKF-Native** | No translation layer. The on-disk format *is* the in-memory model. |
| **Progressive Disclosure** | Tree navigation via `index.md`; graph navigation via Markdown links. |
| **Permissive Consumption** | Follow OKF §9: tolerate missing optional fields, unknown types, broken links. |
| **Producer/Consumer Independence** | Producers emit; consumers render. No round-trip coupling. |
| **Extensibility by Default** | Custom frontmatter keys, custom concept types, plugin architecture. |

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| OKF bundle rendering (tree + graph) | General-purpose Markdown wiki (non-OKF) |
| Full-text search over frontmatter + body | Real-time collaborative editing (Phase 3+) |
| Interactive graph visualization (Cytoscape.js) | WYSIWYG editor (Markdown source only in MVP) |
| Bundle create/import/export/validate | Fine-grained ACL (Phase 3+) |
| Inline Markdown editor with frontmatter form | Plugin marketplace (Phase 4) |
| Multi-bundle federation | Enterprise SSO/SAML (Phase 3+) |

---

## 2. Core Data Model

### 2.1 Bundle

A **bundle** is a directory tree of UTF-8 encoded `.md` files. The directory structure is domain-independent — producers organize concepts as they see fit.

| Property | Specification |
|----------|---------------|
| **Root** | Any directory containing at least one non-reserved `.md` file |
| **Distribution** | Git repository (recommended), tarball, or subdirectory |
| **Version Declaration** | `okf_version: "0.1"` in bundle-root `index.md` frontmatter (only place frontmatter allowed in `index.md`) |

### 2.2 Concept

A **concept** is one Markdown file with YAML frontmatter + body.

| Element | Specification |
|---------|---------------|
| **File Extension** | `.md` (required) |
| **Concept ID** | File path relative to bundle root, with `.md` stripped (e.g., `tables/users.md` → `tables/users`) |
| **Path Segment Regex** | `[A-Za-z0-9_][A-Za-z0-9_.-]*` (alphanumeric/underscore start; alphanumeric, underscore, dot, hyphen thereafter) |
| **Reserved Filenames** | `index.md`, `log.md` — MUST NOT be used for concept documents |

### 2.3 Frontmatter

YAML block delimited by `---` on line 1 and a closing `---`.

#### Required Field (Spec)

| Field | Type | Description |
|-------|------|-------------|
| `type` | Short string | Identifies the kind of concept. **Non-empty required.** No central registry. Consumers MUST tolerate unknown types. |

#### Recommended Fields (Spec)

| Field | Type | Description |
|-------|------|-------------|
| `title` | String | Human-readable display name. Consumers MAY derive from filename if omitted. |
| `description` | String | Single-sentence summary. Used by `index.md` generators, search snippets, previews. |
| `resource` | URI | Canonical URI for the underlying asset. Absent for abstract concepts. |
| `tags` | List of strings | Cross-cutting categorization. |
| `timestamp` | ISO 8601 datetime | Last meaningful change (e.g., `2026-06-17T14:30:00Z`). |

#### Extension Policy

> "Producers MAY include any additional keys. Consumers SHOULD preserve unknown keys when round-tripping and SHOULD NOT reject documents with unrecognized fields." — *OKF SPEC.md §4.1*

### 2.4 Body

Standard CommonMark / GFM Markdown. Three conventional headings have soft-semantic meaning:

| Heading | Purpose |
|---------|---------|
| `# Schema` | Structured description of asset columns/fields (typically a Markdown table) |
| `# Examples` | Concrete usage examples, often fenced code blocks |
| `# Citations` | Numbered external sources backing claims |

All other body structure is producer-defined.

### 2.5 Reserved Files

| Filename | Purpose | Frontmatter |
|----------|---------|-------------|
| `index.md` | Directory listing for progressive disclosure. Body-only (sections grouping child concepts by type). Bundle-root `index.md` MAY contain `okf_version` frontmatter. | None (except root) |
| `log.md` | Optional chronological history. Date headings in ISO 8601 `YYYY-MM-DD`. Leading bold word (`**Update**`, `**Creation**`, `**Deprecation**`) is convention. | None |

---

## 3. Graph Structure

An OKF bundle is **simultaneously a tree and a graph**:

| Structure | Source | Purpose |
|-----------|--------|---------|
| **Tree edges** | Filesystem hierarchy (parent/child directories) | Progressive disclosure via `index.md` |
| **Graph edges** | Markdown links in concept bodies | Rich relationships (joins, references, dependencies) |

### 3.1 Link Forms

| Form | Syntax | Resolution | Spec Status |
|------|--------|------------|-------------|
| **Absolute (bundle-relative)** | `[text](/tables/users.md)` | Against bundle root | **Recommended** |
| **Relative** | `[text](./sibling.md)` or `[text](../parent.md)` | Against source document's directory | Supported |

### 3.2 Link Semantics

- Links are **untyped directed edges**. Relationship type (parent/child, references, joins-with, depends-on) is conveyed by surrounding prose, not link syntax.
- **Broken links are tolerated** (SPEC §5.3): "a link whose target does not exist in the bundle is not malformed; it may simply represent not-yet-written knowledge."
- External links (containing `://`) are rendered but not included in the internal graph.

### 3.3 Index.md as Progressive Disclosure Primitive

Per SPEC §6, `index.md` provides a directory listing grouped by concept type:

```markdown
# Tables
- [customers](/tables/customers.md) — Customer master data
- [orders](/tables/orders.md) — Order transaction log

# Playbooks
- [incident-response](/playbooks/incident-response.md) — On-call runbook

# Subdirectories
- [metrics](/metrics/index.md)
```

Producers MAY auto-generate; consumers MAY synthesize on-the-fly when absent.

---

## 4. Conformance Rules

Per OKF SPEC §9, a bundle is conformant with OKF v0.1 **iff**:

1. **Parseable Frontmatter**: Every non-reserved `.md` file contains a parseable YAML frontmatter block (delimited by `---` on line 1).
2. **Non-empty Type**: Every frontmatter block contains a non-empty `type` field.
3. **Reserved File Structure**: Every `index.md` and `log.md` follows the structure described in SPEC §6 and §7 respectively when present.

### Consumer MUST NOT Reject For:

- Missing optional frontmatter fields (`title`, `description`, `resource`, `tags`, `timestamp`)
- Unknown `type` values
- Unknown additional frontmatter keys (extension fields)
- Broken cross-links
- Missing `index.md` files

> **Rationale**: This permissive model ensures bundles remain useful as they grow, are refactored, and are partially generated by agents.

---

## 5. Wiki Feature Mapping

Each feature below maps to OKF primitives with explicit acceptance criteria.

### 5.1 Page System

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-PS-01** | Each OKF concept renders as a wiki page with: rendered Markdown body, metadata sidebar (type, title, description, resource, tags, timestamp), and concept ID display. |
| **REQ-PS-02** | Missing optional frontmatter fields display as "—" (not an error). |
| **REQ-PS-03** | Unknown `type` values render with a generic icon/color; no crash. |
| **REQ-PS-04** | Extension frontmatter fields render in an "Additional Metadata" collapsible section. |
| **REQ-PS-05** | `index.md` files render as directory landing pages (not editable as concepts). |
| **REQ-PS-06** | `log.md` files render as read-only history timelines. |

### 5.2 Navigation

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-NAV-01** | **Tree Browser**: Collapsible sidebar showing bundle directory structure. `index.md` files shown as folder nodes with synthesized descriptions. Clicking a concept loads it in the main pane. |
| **REQ-NAV-02** | **Graph Browser**: Interactive node-link diagram (Cytoscape.js) showing all concepts as nodes, relative Markdown links as edges. |
| **REQ-NAV-03** | **Breadcrumbs**: Display concept ID path (e.g., `tables → customers`) with clickable ancestors. |
| **REQ-NAV-04** | **Backlinks Panel**: For the current concept, list all concepts that link to it (computed from reverse graph edges). |
| **REQ-NAV-05** | **Deep Linking**: URL format `/wiki/<bundle>/<concept-id>` loads the concept directly. Tree and graph state synchronize with URL. |
| **REQ-NAV-06** | **Keyboard Navigation**: Arrow keys traverse tree; `g` opens graph; `/` focuses search; `Esc` closes panels. |

### 5.3 Search

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-SRCH-01** | Full-text search across: `title`, `description`, `body`, `tags`, `type`. |
| **REQ-SRCH-02** | Type filter: dropdown of all distinct `type` values in bundle; multi-select. |
| **REQ-SRCH-03** | Tag filter: multi-select from all distinct tag values. |
| **REQ-SRCH-04** | Results ranked by: exact title match > frontmatter match > body match. Snippet shows highlighted match context. |
| **REQ-SRCH-05** | Search index built incrementally on bundle load; updates within 500ms of file change. |
| **REQ-SRCH-06** | "Search as you type" with 150ms debounce; results virtualized for >1000 hits. |

### 5.4 Graph Visualization

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-GV-01** | Interactive Cytoscape.js graph: pan, zoom, drag nodes. |
| **REQ-GV-02** | Nodes colored by `type` (extensible palette; unknown types get default color). |
| **REQ-GV-03** | Node size proportional to degree (configurable: uniform, degree, pagerank). |
| **REQ-GV-04** | Click node → detail panel with frontmatter + rendered body + backlinks. |
| **REQ-GV-05** | Layout switcher: `cose` (force-directed), `dagre` (hierarchical), `grid`, `circle`, `concentric`. |
| **REQ-GV-06** | Filter panel: by type, by tag, by degree range, show/hide isolated nodes. |
| **REQ-GV-07** | "Focus mode": double-click node → center + 2-hop neighborhood; breadcrumb to return. |
| **REQ-GV-08** | Export graph as PNG/SVG/GraphML. |
| **REQ-GV-09** | Graph built from **relative links only** (per reference viewer behavior); absolute and external links rendered in body but not as edges. |

### 5.5 Bundle Management

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-BM-01** | **Create Bundle**: Wizard → name, root directory, optional git init, optional `okf_version` in root `index.md`. |
| **REQ-BM-02** | **Import Bundle**: Select directory or upload tarball/zip; validate on import (see REQ-BM-04). |
| **REQ-BM-03** | **Export Bundle**: Download as tarball/zip; option to include/exclude `.git`. |
| **REQ-BM-04** | **Validate Bundle**: Run OKF conformance checks (§4). Report: errors (blocking), warnings (missing recommended fields, broken links), info (unknown types, extension keys). |
| **REQ-BM-05** | **Auto-generate index.md**: Per-directory `index.md` with type-grouped sections, descriptions from frontmatter, subdirectory links. LLM-synthesized directory descriptions (optional, configurable). |
| **REQ-BM-06** | **Regenerate log.md**: Optional; create `log.md` from git history (commits touching each directory). |
| **REQ-BM-07** | **Bundle Metadata**: Display concept count, type distribution, tag cloud, last modified, `okf_version`. |

### 5.6 Versioning

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-VER-01** | Git-based versioning: every save creates a commit with message template: `okf: <action> <concept-id> — <summary>`. |
| **REQ-VER-02** | History view per concept: list commits, show diff (frontmatter + body). |
| **REQ-VER-03** | Bundle-level history: timeline of all commits with bundle stats. |
| **REQ-VER-04** | `okf_version` in root `index.md` frontmatter displayed in bundle metadata; warning if missing or mismatched. |
| **REQ-VER-05** | Restore previous version of a concept (creates new commit reverting changes). |

### 5.7 Editing

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-ED-01** | **Inline Markdown Editor**: Split view (source / live preview) or tabbed. Toolbar for headings, lists, links, code blocks, tables. |
| **REQ-ED-02** | **Frontmatter Form**: Side panel or modal with fields for all recommended keys + dynamic extension field editor (add/remove key-value). |
| **REQ-ED-03** | **Link Autocomplete**: Typing `[` triggers fuzzy search over concept IDs; selection inserts `[title](/path.md)`. |
| **REQ-ED-04** | **Type Validation**: On save, warn if `type` is empty; suggest known types from bundle. |
| **REQ-ED-05** | **Concept Creation**: "New Concept" → choose parent directory, type (from known types or custom), pre-fill frontmatter template. |
| **REQ-ED-06** | **Concept Deletion**: Move to `.okf/trash/` with `log.md` entry; restore within 30 days. |
| **REQ-ED-07** | **Rename/Move**: Update concept ID (file path); **rewrite all internal links** pointing to old ID (with preview/dry-run). |
| **REQ-ED-08** | **Conflict Detection**: If file changed on disk since load, show diff and merge options. |

### 5.8 Multi-Bundle Support

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-MB-01** | **Bundle Registry**: Workspace contains multiple bundles; sidebar switches between them. |
| **REQ-MB-02** | **Cross-Bundle Links**: Syntax `[text](@bundle-name:/path.md)` resolves to concept in named bundle. |
| **REQ-MB-03** | **Federated Search**: Single query searches across all registered bundles; results tagged with bundle name. |
| **REQ-MB-04** | **Federated Graph**: Toggle to show combined graph; nodes prefixed with bundle identifier. |
| **REQ-MB-05** | **Bundle Dependencies**: Declare `depends_on: [bundle-a, bundle-b]` in root `index.md`; validate on load. |

---

## 6. Producer Requirements

Tools that **emit** OKF bundles (CLI, CI/CD pipelines, LLM agents).

### 6.1 Two-Pass Architecture

| Pass | Description | Deterministic |
|------|-------------|---------------|
| **Pass 1: Extract** | Walk filesystem / source system; emit minimal concepts with `type`, `title`, `description`, `resource`. No LLM. | Yes |
| **Pass 2: Enrich** | LLM pass per concept: add schema, examples, citations, cross-links, refined descriptions. | No (LLM) |

### 6.2 Producer CLI/API Requirements

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-PROD-01** | `okf-producer extract <source> --output <bundle-dir>` — deterministic extraction. |
| **REQ-PROD-02** | `okf-producer enrich <bundle-dir> --model <llm-model> --passes <n>` — LLM enrichment. |
| **REQ-PROD-03** | **Concept ID Validation**: Reject paths violating segment regex; auto-sanitize option. |
| **REQ-PROD-04** | **Link Validation**: After emission, scan all links; report broken internal links as warnings; external links as info. |
| **REQ-PROD-05** | **Auto index.md Generation**: Run after each pass; group by `type`; include LLM-synthesized directory descriptions (configurable). |
| **REQ-PROD-06** | **Provenance in log.md**: Record pass, timestamp, model, prompt hash, source commit. |
| **REQ-PROD-07** | **Incremental Updates**: Detect changed source files; re-extract/enrich only affected concepts. |
| **REQ-PROD-08** | **Template System**: Per-type frontmatter + body templates (Jinja2/Go templates). |

---

## 7. Consumer Requirements

Tools that **read and render** OKF bundles (wiki UI, graph viewer, search index, LLM context loaders).

### 7.1 Parsing

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-CONS-01** | Parse frontmatter with `yaml.safe_load` (no arbitrary object instantiation). |
| **REQ-CONS-02** | `---` delimiter MUST be on line 1 (no leading whitespace/BOM). Files without valid frontmatter → empty frontmatter, whole file as body (graceful fallback). |
| **REQ-CONS-03** | Non-mapping YAML → error (per reference implementation). |
| **REQ-CONS-04** | Preserve all frontmatter keys (including unknown/extension keys) for round-trip. |

### 7.2 Rendering

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-CONS-05** | Render Markdown body with **marked.js** (or equivalent CommonMark/GFM compliant parser). |
| **REQ-CONS-06** | **Rewire Internal Links**: Transform `[text](/path.md)` and `[text](./path.md)` to in-app navigation (SPA route or viewer node focus). External links (`://`) open in new tab. |
| **REQ-CONS-07** | Syntax highlighting for fenced code blocks (Prism.js or shiki). |
| **REQ-CONS-08** | Render `index.md` as directory landing page (not as a concept). |
| **REQ-CONS-09** | Render `log.md` as timeline. |

### 7.3 Graph Construction

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-CONS-10** | Extract edges from **relative Markdown links only** (regex: `\]\(([^)\s]+\.md)(?:#[A-Za-z0-9_-]*)?\)`). |
| **REQ-CONS-11** | Resolve relative paths against source document's directory; normalize to bundle-relative concept ID (strip `.md`). |
| **REQ-CONS-12** | Drop edges to non-existent concepts (silently, per SPEC §5.3). |
| **REQ-CONS-13** | Build reverse index for backlinks panel. |

### 7.4 Search & Filter

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-CONS-14** | Build inverted index over `title`, `description`, `body`, `tags`, `type`. |
| **REQ-CONS-15** | Type filter: populate from distinct `type` values in bundle. |
| **REQ-CONS-16** | Tag filter: populate from distinct tag values across all concepts. |
| **REQ-CONS-17** | Search results include: concept ID, title, type, snippet, score. |

### 7.5 Extensible Type Color Palette

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-CONS-18** | Built-in color map for common types (Table, View, Metric, Playbook, Runbook, API, Model, etc.). |
| **REQ-CONS-19** | Unknown types assigned deterministic hash-based color. |
| **REQ-CONS-20** | User-configurable palette override (JSON file: `type → #hex`). |

### 7.6 Single-File HTML Viewer Option

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-CONS-21** | `okf-viewer export --bundle <dir> --output viewer.html` produces self-contained HTML with embedded CSS/JS/bundle JSON. |
| **REQ-CONS-22** | Viewer works offline (no CDN dependencies; all assets inlined). |
| **REQ-CONS-23** | Viewer < 5 MB gzipped. |

---

## 8. API Requirements

REST and/or GraphQL API for programmatic access.

### 8.1 REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bundles` | GET | List registered bundles (name, path, concept count, okf_version) |
| `/api/bundles/{bundle}` | GET | Bundle metadata + type/tag distributions |
| `/api/bundles/{bundle}/concepts` | GET | Paginated list of concepts (filter: type, tag, path prefix) |
| `/api/bundles/{bundle}/concepts/{concept-id}` | GET | Full concept: frontmatter + rendered HTML + raw Markdown |
| `/api/bundles/{bundle}/concepts/{concept-id}` | PUT | Update concept (frontmatter + body); returns new commit SHA |
| `/api/bundles/{bundle}/concepts/{concept-id}` | DELETE | Move to trash; returns restore token |
| `/api/bundles/{bundle}/concepts` | POST | Create new concept; returns concept ID |
| `/api/bundles/{bundle}/search` | GET/POST | Full-text search (q, type[], tag[], limit, offset) |
| `/api/bundles/{bundle}/graph` | GET | Cytoscape.js-compatible JSON: `{ nodes: [], edges: [] }` |
| `/api/bundles/{bundle}/graph/backlinks/{concept-id}` | GET | Array of concept IDs linking to target |
| `/api/bundles/{bundle}/validate` | POST | Run conformance check; return { errors, warnings, info } |
| `/api/bundles/{bundle}/index/regenerate` | POST | Regenerate all `index.md` files |
| `/api/bundles/{bundle}/export` | GET | Stream tarball/zip |

### 8.2 GraphQL Schema (Core Types)

```graphql
type Bundle {
  name: String!
  path: String!
  conceptCount: Int!
  okfVersion: String
  types: [String!]!
  tags: [String!]!
}

type Concept {
  id: String!           # concept ID (path without .md)
  bundle: String!
  frontmatter: JSON!    # all keys preserved
  body: String!         # raw Markdown
  bodyHtml: String!     # rendered HTML
  backlinks: [Concept!]!
  outgoingLinks: [Concept!]!
}

type SearchResult {
  concept: Concept!
  score: Float!
  snippet: String!
  matchedFields: [String!]!
}

type GraphData {
  nodes: [GraphNode!]!
  edges: [GraphEdge!]!
}

type GraphNode {
  id: String!
  label: String!
  type: String!
  color: String!
  degree: Int!
}

type GraphEdge {
  source: String!
  target: String!
  linkText: String!
}
```

### 8.3 Conformance Check API

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-API-01** | `POST /validate` returns `{ conformant: boolean, errors: [], warnings: [], info: [] }` per SPEC §9. |
| **REQ-API-02** | Errors: missing frontmatter, empty `type`, malformed reserved files. |
| **REQ-API-03** | Warnings: missing recommended fields, broken internal links. |
| **REQ-API-04** | Info: unknown types, extension keys, missing `index.md`, missing `okf_version`. |

---

## 9. Non-Functional Requirements

### 9.1 Performance

| Requirement | Target | Notes |
|-------------|--------|-------|
| **REQ-NF-01** | Bundle load (10K concepts) | < 3 seconds cold; < 500ms warm (sidecar index) |
| **REQ-NF-02** | Concept render | < 100ms (marked.js + frontmatter) |
| **REQ-NF-03** | Graph render (10K nodes) | < 2 seconds initial layout (WebGL renderer) |
| **REQ-NF-04** | Search query (10K concepts) | < 200ms p95 (inverted index + BM25) |
| **REQ-NF-05** | Incremental index update | < 500ms per changed file |
| **REQ-NF-06** | Single-file HTML viewer | < 5 MB gzipped |

### 9.2 Scalability

| Requirement | Target |
|-------------|--------|
| **REQ-NF-07** | Support 100,000 concepts per bundle (streaming parse, virtualized UI, paginated APIs) |
| **REQ-NF-08** | Support 50 concurrent bundles in workspace |
| **REQ-NF-09** | Horizontal scaling: stateless API pods + shared object storage for bundles |

### 9.3 Governance Gaps to Fill (Post-MVP)

| Gap | Description | Priority |
|-----|-------------|----------|
| **ACL / RBAC** | Per-bundle, per-concept read/write/admin; integrate with OIDC/SAML | High |
| **PII Detection** | Scan frontmatter/body for PII patterns; flag or redact | High |
| **Stewardship** | Assign owners per type or path prefix; review workflow for changes | Medium |
| **Signing/Attestation** | Cryptographic signing of bundles (cosign/sigstore); verify on import | Medium |
| **Audit Log** | Immutable log of all mutations (who, what, when, diff) | High |
| **Retention Policy** | Auto-archive/delete concepts by tag/type/age | Low |

### 9.4 Interoperability

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-NF-10** | **MCP Server**: Expose `read_concept`, `search`, `graph`, `validate` as MCP tools for LLM agents. |
| **REQ-NF-11** | **A2A Payload**: Concept documents serializable as A2A `Artifact` (JSON with `type`, `frontmatter`, `body`). |
| **REQ-NF-12** | **Catalog Export**: Generate Data Catalog / Unity Catalog / Collibra import format from bundle. |
| **REQ-NF-13** | **Catalog Import**: Ingest Data Catalog entries as OKF concepts (reverse of above). |

#### Standards Comparison

OKF deliberately does not replace the standards it overlaps with — it is the **portable exchange layer** among them. The relationship is complementary, not competitive. *(Research 01 §5)*

| Standard | Role | Relationship to OKF |
|----------|------|---------------------|
| **RDF / OWL** | Formal knowledge, inference | Complements; OKF references schemas, does not subsume. No inference/entailment. |
| **KG products** (Dataplex, Unity, Collibra) | Operated, queryable catalogs | OKF is the portable export/import format. |
| **Schema.org** | Type vocabulary for web data | Complements; types embeddable as JSON-LD in body. OKF types are producer-defined. |
| **Karpathy Wiki / Obsidian / AGENTS.md** | LLM-wiki family | OKF is the **interoperable subset** — formalizing the pattern for cross-team cooperation. |
| **Avro / Protobuf / OpenAPI** | Domain schemas | Complements; referenced in `# Schema` sections. |
| **JSON-LD / YAML / TOML** | Serialization formats | Different shape — Markdown+YAML chosen for familiarity. |
| **Feast / Tecton / Atlan** | ML / data catalogs | Adjacent; OKF is the exchange layer. |
| **Hugo / Docusaurus / MkDocs** | Doc site generators | Familiar authoring surface; bundles publishable through them. |

> **Design point:** OKF sits at the opposite end of the spectrum from OWL — deliberately shallow in formal semantics, deliberately deep in operational simplicity. The bet is that the next generation of knowledge is consumed by LLMs, not SPARQL engines, so the semantics come from the model, not the format.

### 9.5 Extensibility

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-NF-14** | **Plugin Interface**: Load WASM/JS plugins for: custom renderers (per type), custom validators, custom index.md synthesizers, custom search rankers. |
| **REQ-NF-15** | **Custom Type Registry**: Bundle-level `types.yaml` mapping type → { icon, color, template, validator }. |
| **REQ-NF-16** | **Hook System**: Pre-save, post-save, pre-index-gen, post-import hooks (sync + async). |

---

## 10. Implementation Phases

### Phase 1: MVP — Core Wiki (Weeks 1–8)

| ID | Deliverable | Description |
|----|-------------|-------------|
| **P1-1** | **Data Model & Parser** | `okf-core` library: `Concept`, `Bundle`, `Frontmatter` types; `parse_file()`, `serialize()`, `validate()` per SPEC §9. |
| **P1-2** | **Tree Navigator** | React/Vue component: collapsible tree from bundle FS; `index.md` as folder nodes; deep linking. |
| **P1-3** | **Concept Renderer** | Marked.js + Prism.js; frontmatter sidebar; rewire internal links for SPA nav. |
| **P1-4** | **Search Engine** | Lunr.js or MiniSearch index over title/description/body/tags/type; type/tag filters; snippet highlighting. |
| **P1-5** | **Graph Visualizer** | Cytoscape.js viewer: nodes from concepts, edges from relative links; type color palette; layout switcher; detail panel + backlinks. |
| **P1-6** | **Single-File HTML Export** | `okf-viewer export` → self-contained `viewer.html` with embedded bundle JSON. |
| **P1-7** | **Bundle Validation CLI** | `okf validate <bundle>` → conformance report (errors/warnings/info). |
| **P1-8** | **Dev Server** | `okf serve <bundle>` — hot-reload wiki on localhost. |

**Exit Criteria**: All P1 items demoable; 10K-concept bundle loads < 3s; search < 200ms; graph renders.

### Phase 2: Authoring & Quality (Weeks 9–16)

| ID | Deliverable | Description |
|----|-------------|-------------|
| **P2-1** | **Inline Markdown Editor** | Monaco/CodeMirror editor with split preview; toolbar; frontmatter form panel. |
| **P2-2** | **Link Autocomplete** | `[[` trigger → fuzzy search concept IDs → insert `[title](/path.md)`. |
| **P2-3** | **Concept CRUD UI** | Create (template per type), rename/move (link rewrite preview), delete (trash + restore). |
| **P2-4** | **Link Validator** | Background scan; broken link report; quick-fix (create target, remove link). |
| **P2-5** | **Index.md Generator** | `okf index regen` — per-directory `index.md` with type-grouped sections; LLM-synthesized descriptions (optional). |
| **P2-6** | **Git Integration** | Auto-commit on save; history panel per concept; diff view; restore version. |
| **P2-7** | **Bundle Import/Export UI** | Drag-drop tarball/zip; validate on import; export with/without `.git`. |

**Exit Criteria**: End-to-end edit cycle works; link rewrite correct; git history usable.

### Phase 3: Multi-Bundle & Governance (Weeks 17–28)

| ID | Deliverable | Description |
|----|-------------|-------------|
| **P3-1** | **Workspace / Bundle Registry** | Multi-bundle sidebar; add/remove bundles; per-bundle config. |
| **P3-2** | **Cross-Bundle Links** | Syntax `@bundle:/path.md`; resolve in editor, viewer, graph, search. |
| **P3-3** | **Federated Search** | Single query across bundles; results grouped by bundle. |
| **P3-4** | **Federated Graph** | Combined graph with bundle-prefixed node IDs; bundle filter. |
| **P3-5** | **RBAC / ACL** | Per-bundle roles (viewer, editor, admin); OIDC integration. |
| **P3-6** | **PII Scanner** | Regex/ML-based detection on save; block or warn. |
| **P3-7** | **Stewardship Workflow** | Type/path owners; PR-style review for changes to owned concepts. |
| **P3-8** | **Bundle Signing** | `okf sign <bundle>` → cosign bundle manifest; `okf verify` on import. |
| **P3-9** | **MCP Server** | `okf-mcp` exposing read/search/graph/validate tools. |

**Exit Criteria**: Multi-bundle workspace demo; governance features auditable.

### Phase 4: Enterprise & Ecosystem (Weeks 29–44)

| ID | Deliverable | Description |
|----|-------------|-------------|
| **P4-1** | **Catalog Connectors** | Bi-directional: Data Catalog ↔ OKF, Unity Catalog ↔ OKF, Collibra ↔ OKF. |
| **P4-2** | **A2A Integration** | Concept as A2A Artifact; agent-to-agent knowledge exchange. |
| **P4-3** | **Plugin System** | WASM plugin SDK; marketplace (local registry); example plugins: Mermaid renderer, OpenAPI importer, DBT model extractor. |
| **P4-4** | **Query Language** | `okf-query` DSL: `type:Table AND tags:pii AND description:~"customer"` → concept IDs; usable in CLI, API, MCP. |
| **P4-5** | **Semantic Search** | Embedding-based search (local or API); hybrid BM25 + vector. |
| **P4-6** | **LLM Context Loader** | `okf context <concept-id> --depth 2` → concatenated Markdown for LLM context window (with token budget). |
| **P4-7** | **Enterprise SSO/SCIM** | SAML/OIDC + provisioning. |
| **P4-8** | **Audit & Compliance Dashboard** | Immutable audit log; compliance reports (GDPR, SOC2). |

**Exit Criteria**: Production-ready for enterprise deployment; ecosystem integrations verified.

---

## 11. Agent Integration

OKF is the **content layer** that agent protocols sit on top of. Three open protocols define how agents share state; OKF is the fourth: *"what the knowledge looks like once loaded."* Framing: *"OKF is to MCP what HTML is to HTTP — HTTP moves bits, HTML renders them."* *(Research 03 §4.1)*

| Protocol | Scope | Analogy to OKF |
|----------|-------|----------------|
| **MCP** | Tool / resource access | Lower layer: "how an agent reaches a file" |
| **A2A** | Inter-agent task handoff | Sibling layer: "how two agents pass a job" |
| **Context Engineering** | What goes into LLM context | Orthogonal: "how an agent decides what to load" |
| **OKF v0.1** | Knowledge representation | **This layer: "what the knowledge looks like once loaded"** |

### 11.1 MCP Resource Mapping (okf:// URI Scheme)

MCP defines resources as *named, addressable* content. An OKF bundle maps directly: concept ID (file path) becomes the URI scheme — `okf://<bundle>/concepts/tables/users.md`. The resource's `text` is the Markdown body; its metadata is the frontmatter (all keys preserved).

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-AGT-01** | MCP server exposes each OKF concept as an addressable resource under the `okf://<bundle>/concepts/<path>` URI scheme. |
| **REQ-AGT-02** | MCP `read_resource(okf://...)` returns frontmatter as metadata and Markdown body as text. |
| **REQ-AGT-03** | MCP tools `search`, `graph`, `validate`, `list_concepts` operate over the bundle. |

### 11.2 A2A Payload Pattern

A2A's handoff protocol specifies a structured `Artifact` type. An OKF bundle is a natural concrete representation: a self-contained directory of concepts the receiving agent reads without translation. The `resource:` frontmatter gives a stable handle to the canonical asset; the `# Citations` block lets the agent verify claims.

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-AGT-04** | Concept serializable as A2A `Artifact` JSON: `{ type, frontmatter, body }`. |
| **REQ-AGT-05** | Bundle exportable as A2A-compatible directory payload for agent handoff. |

### 11.3 Multi-Agent Orchestration with Shared Bundles

A shared knowledge base is a prerequisite for multi-agent coordination. OKF bundles satisfy this portably: each agent subscribes via git pull, MCP server, or custom fetcher and sees the same knowledge graph. **Concrete pattern**: a "router" agent loads the relevant subset of the bundle into context (by `type` filter) and passes it to a specialist agent; the specialist's response is captured as a `type: Q&A` concept with citations — the conversation becomes Episodic memory.

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-AGT-06** | Wiki supports read-only bundle clone/subscription (git pull, tarball fetch) for multi-agent consumers. |
| **REQ-AGT-07** | `okf context <concept-id> --depth N` loads a concept and its N-hop graph neighborhood as concatenated Markdown (with token budget). |
| **REQ-AGT-08** | Type-filtered context export: load all concepts of a given `type` (or set) into a single context payload. |

### 11.4 Human-AI Collaborative Workflows & 11.5 Agent Context Sharing

OKF supports human+AI artifact co-production: a human authors a `type: Runbook`, an AI proposes `type: Example` additions, a CI bot validates the bundle, a reviewer approves the PR — same file at every step. The dominant pattern for agent persistent memory is *Markdown files in a directory*; OKF formalizes this with conformance rules. The same memory bundle loads into Claude, Gemini, GPT-4o, or a custom model without translation.

| Requirement | Acceptance Criteria |
|-------------|---------------------|
| **REQ-AGT-09** | Git-based review workflow (PR/diff) works for both human-authored and agent-authored concepts — same file format. |
| **REQ-AGT-10** | CI hook can run `okf validate` on PRs; block merge on conformance errors. |
| **REQ-AGT-11** | Bundle usable as agent memory store: drop into context directory; agent reads via MCP or direct file access. |
| **REQ-AGT-12** | No provider-specific serialization — same `.md` files load into any LLM. |

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Bundle** | Unit of distribution: a directory tree of OKF concept files. |
| **Concept** | Unit of knowledge: one `.md` file with YAML frontmatter + Markdown body. |
| **Concept ID** | File path relative to bundle root, minus `.md` (e.g., `tables/users`). |
| **Frontmatter** | YAML block between `---` delimiters at file start. |
| **index.md** | Reserved filename: directory landing page for progressive disclosure. |
| **log.md** | Reserved filename: optional chronological history. |
| **okf_version** | Version field in root `index.md` frontmatter (e.g., `"0.1"`). |
| **Producer** | Tool/system that emits OKF bundles. |
| **Consumer** | Tool/system that reads and renders OKF bundles. |

---

## Appendix B: Reference Links

| Resource | URL |
|----------|-----|
| OKF Specification (SPEC.md) | `GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md` |
| GCP Blog Announcement | "How the Open Knowledge Format can improve data sharing" |
| Reference Implementation | `GoogleCloudPlatform/knowledge-catalog/okf/` (enrichment-agent, viewer) |
| Sample Bundles | `bundles/ga4`, `bundles/stackoverflow`, `bundles/crypto_bitcoin` |
| Karpathy LLM Wiki Gist | https://gist.github.com/karpathy/... |

---

## Appendix C: Acceptance Test Matrix (Summary)

| Feature Area | Test Count (Est.) | Automation Target |
|--------------|-------------------|-------------------|
| Parser/Conformance | 45 | 100% unit |
| Tree Navigation | 12 | 90% e2e |
| Graph Visualization | 18 | 80% e2e (visual regression) |
| Search | 22 | 100% unit + 90% e2e |
| Editing (CRUD) | 28 | 90% e2e |
| Link Rewriting | 15 | 100% unit |
| Git Integration | 10 | 80% e2e |
| Multi-Bundle | 16 | 85% e2e |
| Governance (RBAC, PII) | 20 | 90% unit + 80% e2e |
| API (REST + GraphQL) | 35 | 100% contract |
| MCP Server | 8 | 90% integration |
| Performance | 10 | Benchmark suite |

**Total Estimated Tests: ~239**

---

## Appendix D: Competitive Landscape

The 2026 enterprise catalog market has three layers: **commercial platforms** (Atlan, Collibra, Alation, Informatica), **open-source platforms** (DataHub, OpenMetadata, Unity Catalog), and **standards** (DCAT, CKAN, STIX, OWL, OKF). OKF is the only entry that is a *format* with no associated platform. *(Research 03 §5)*

### D.1 At-a-Glance Matrix

| System | Type | AI-Agent Native? | Vendor Lock-in | Open Source? |
|--------|------|-------------------|----------------|--------------|
| **Atlan** | Commercial catalog | Yes (Atlan AI) | Medium | No |
| **Collibra** | Commercial catalog + governance | Yes (Collibra AI) | High | No |
| **Alation** | Commercial catalog | Yes | High | No |
| **DataHub** | OSS metadata platform | Partial | Low (self-host) | Yes |
| **OpenMetadata** | OSS metadata platform | Yes | Low | Yes |
| **Unity Catalog** | OSS data + AI catalog (Databricks) | Yes | Medium | Yes |
| **OKF v0.1** | **Open format (no platform)** | **Yes — by design** | **None** | Yes (Apache 2.0) |
| **DCAT** | W3C standard | No | None | Yes |
| **CKAN** | Open data portal | No | None | Yes |
| **STIX 2.0** | OASIS standard (threat intel) | No | None | Yes |
| **OWL / RDF** | W3C standards | Limited (SPARQL agents) | None | Yes |

### D.2 Positioning

**What commercial catalogs do well:** Discovery UI (search, lineage, stewardship workflows refined over years), stewardship & policy (ownership, certification, access control in-platform), deep lineage integration with warehouses/BI/orchestrators, and natural-language AI assistants. OKF bundles are static directories — the *consumer* provides the UI; OKF is the *content* those assistants point at. **What OKF uniquely offers:** Vendor neutrality (no platform owns the bundle), human editability (text editor + PR review), agent-legibility (designed for LLMs, not retrofitted), git-native evolution (reviewable diffs, atomic rollbacks), zero platform license cost. **The agent-protocol lens:** OKF is in a category of one — the only catalog format that is also a first-class format for LLM consumption. Commercial catalogs are adding AI assistants, but their data models are still SQL-shaped and their UIs remain the primary interface. OKF's primary interface is the LLM.

---

## Appendix E: Limitations & Risk Register

OKF v0.1 is deliberately minimal. These nine known gaps must be accounted for in governance and scalability design. *(Research 03 §6)*

| # | Gap | Description | Mitigation | Severity |
|---|-----|-------------|------------|----------|
| **L1** | No query language | No OKFQL/SPARQL/Cypher. Consumers must read all concepts, index downstream, or walk links. | Phase 4 `okf-query` DSL (P4-4); sidecar index per REQ-NF-01. | High |
| **L2** | Scalability | Enterprise catalog = tens of thousands of concepts; loading 10K into LLM context is impossible. Git slow at 1M+ concepts. | Streaming parse (REQ-NF-07); virtualized UI; token-budgeted context loader (P4-6). | High |
| **L3** | v0.1 maturity | Spec is Draft; reference `validate()` stricter than spec. Expect breaking changes in v0.2/v1.0, tooling churn. | Track `okf_version` (REQ-VER-04); design parser for forward-compat. | Medium |
| **L4** | Governance / ACL | No ACL model, no locking, no stewardship. Body can contain PII; no retention/deletion model; no signing. | Phase 3 governance (P3-5 through P3-8); §9.3 gaps table. | High |
| **L5** | Performance at scale | No public benchmarks; reference implementation is unoptimized Python + pyyaml. | Streaming parsers; incremental enrichment; sidecar index (REQ-NF-01/05). | Medium |
| **L6** | Untyped relationships | Links are untyped; consumers can't query "depends-on" without out-of-band convention. | Conventional headings (`# Joins`, `# Depends on`); v0.2 link annotations. | Medium |
| **L7** | Discovery & federation | No bundle registry, no DNS-like discovery, no signed trust metadata. | Multi-bundle registry (REQ-MB-01); bundle dependencies (REQ-MB-05). | Medium |
| **L8** | No formal semantics | No inference/entailment; cross-cloud type inconsistencies not flagged. | Consumers build type-validation on top (REQ-ED-04). | Low |
| **L9** | Community & ecosystem risk | Google-published, not yet multi-stakeholder. Foundation-hosted process (CNCF/OASIS) would de-risk. | Track ecosystem; avoid hard single-vendor dependencies. | Medium |

---

## Appendix F: Reference Adoption Path (90 Days)

For a team that has decided to adopt OKF, a realistic 90-day path, derived from the reference implementation pipeline. *(Research 03 §7.3, §2.1)*

### F.1 Reference Pipeline (Google's Own)

The reference implementation ships a copyable end-to-end pipeline: (1) **Source adapter** — `Source` ABC with `BigQuerySource` (~200 LOC) walking datasets/tables/views/columns; Snowflake/Databricks/PostgreSQL/Salesforce/dbt/REST adapters are mechanical extensions. (2) **Pass 1** — ADK agent reads source metadata, emits one concept per asset. (3) **Pass 2** — second ADK agent seeds a web crawl from canonical doc URLs, adding `# Citations` and `references/<slug>` docs. (4) **Bundle writer** — auto-generates per-directory `index.md`. (5) **Visualizer** — single-file `viz.html`. Invoked per "recipe" — the **recipe + bundle** pairing encodes reproducibility next to the artifact.

### F.2 Generic Enterprise Pipeline

| Stage | Purpose | Failure Modes |
|-------|---------|---------------|
| **Connect** | Reach data sources (DBs, warehouses, catalogs, wikis, CRMs) via custom adapters, JDBC/ODBC, dbt manifest parsers, or vendor APIs | Auth drift, schema drift, rate limits |
| **Extract metadata** | Pull table/view/column/business-term metadata into normalized form (SchemaCrawler, DataHub GMS, Unity Catalog APIs) | Inconsistent naming, missing descriptions |
| **Draft concepts** | Emit OKF concept docs with required + recommended frontmatter (LLM for descriptions, templating for deterministic fields) | Hallucinated schemas, missing `type`, broken links |
| **Enrich** | Add citations, examples, join paths, runbooks via second LLM pass + cross-reference crawl + human review queue | Citation drift, outdated examples |
| **Serve** | Render bundle to humans/agents/downstream systems via static viewer, git repo, Knowledge Catalog ingest, or MCP server | Stale bundles, broken cross-links, large bundles |

### F.3 90-Day Adoption Timeline

| Phase | Window | Actions |
|-------|--------|---------|
| **Scope & Pilot** | Days 0–14 | Pick one domain (e.g. warehouse glossary). Define minimal `type` set (Table, Column, Metric, Runbook). Hand-author 10–20 concepts. |
| **Build Producer** | Days 15–30 | Use reference enrichment agent as template. Add a source adapter for the team's warehouse (BigQuery, Snowflake, Databricks). Set up recipe + bundle pattern. |
| **Build Consumer** | Days 31–60 | Set up MCP server or static viewer. Wire into at least one agent (Claude, Gemini, in-house). Set up CODEOWNERS and a PR template for governance. |
| **Expand & Federate** | Days 61–90 | Onboard a second domain (e.g. CRM glossary). Define a cross-bundle mapping. Publish the bundle internally and to one external party (partner or auditor). |

---

## Appendix G: Technical Reference — Reference Implementation Architecture

The OKF reference implementation (`GoogleCloudPlatform/knowledge-catalog/okf/`) is a working end-to-end pipeline that informs the producer and consumer requirements above. *(Research 02 §5)*

### G.1 Package Structure (`enrichment-agent`)

```
enrichment_agent/
├── agent.py          # Two ADK Agent instances (BQ pass + Web pass)
├── runner.py         # Orchestrates the two-pass pipeline
├── bundle/
│   ├── document.py   # OKFDocument: parse / serialize / validate
│   ├── index.py      # regenerate_indexes() — auto index.md generation
│   └── synthesizer.py# LLM-based directory description synthesis
├── sources/
│   ├── base.py       # Source ABC + ConceptRef dataclass
│   └── bigquery.py   # BigQuerySource adapter (~200 LOC)
├── tools/
│   ├── bundle_tools.py   # read_existing_doc, write_concept_doc
│   ├── source_tools.py   # list_concepts, read_concept_raw, sample_rows
│   └── web_tools.py      # fetch_url (web pass's only tool)
├── prompts/
│   ├── enrichment_instruction.md      # Pass 1 prompt (4 KB)
│   └── web_ingestion_instruction.md   # Pass 2 prompt (11.5 KB)
└── viewer/
    └── generator.py   # generate_visualization() — static HTML writer
```

### G.2 Two-Pass Pipeline

| Pass | Instruction | Tools | Output |
|------|-------------|-------|--------|
| **Pass 1 (Source)** | `enrichment_instruction.md` (4 KB) | `list_concepts`, `read_concept_raw`, `sample_rows`, `read_existing_doc`, `write_concept_doc` | One `.md` per source concept; sharded tables collapsed into wildcard families |
| **Pass 2 (Web)** | `web_ingestion_instruction.md` (11.5 KB) | Above + `fetch_url` | Enriched concepts, `references/<slug>` docs, citations |
| **Post-pass** | — | `regenerate_indexes()` | Per-directory `index.md` with type-grouped sections + LLM-synthesized descriptions |

**Budget enforcement** (Pass 2): `--web-max-pages` (default 100), `--web-allowed-host`, `--web-allowed-path-prefix`, `--web-denied-path-substring`, `--web-max-depth`. The agent cannot overrun.

### G.3 BigQuerySource Adapter

Implements the `Source` ABC (`list_concepts`, `read_concept`, `sample_rows`, `find`). Emits one `BigQuery Dataset` concept per dataset, then walks tables. Tables matching shard pattern `^(prefix)(_)(\d{6,8})$` are collapsed into a **family concept** with wildcard `resource` URI ending `/*`. Extracts schema (recursive `SchemaField` walk), partitioning, clustering, labels, row/byte counts. `sample_rows` falls back to `SELECT * ... LIMIT N` for VIEW / MATERIALIZED_VIEW / EXTERNAL / SNAPSHOT (tabledata.list REST endpoint refuses non-base tables).

### G.4 Viewer Generator (`generate_visualization`)

1. `rglob` every `*.md`, skip `index.md`, parse each with `OKFDocument.parse` (silently skip failures).
2. Extract relative links via regex, resolve against document directory + bundle root, normalize to concept IDs.
3. Build Cytoscape nodes (type-colored, size by body length) and edges (filtered to existing targets, deduplicated).
4. Load `templates/viz.html` (with `__BUNDLE_NAME__` / `__BUNDLE_DATA__` placeholders) + `static/viz.css` + `static/viz.js`.
5. Embed bundle as JSON in `window.BUNDLE`; write single HTML file (openable from `file://`, committable as artifact).

### G.5 Sample Bundles

| Sample | Public Dataset | Topology Pattern |
|--------|----------------|------------------|
| **GA4** | `bigquery-public-data.ga4_obfuscated_sample_ecommerce` | Single denormalized events table (`events_*`) + reference docs. Tests wildcard-family handling. |
| **Stack Overflow** | `bigquery-public-data.stackoverflow` | Many independent entity tables. Tests multi-concept enrichment from one schema-docs page. |
| **Bitcoin** | `bigquery-public-data.crypto_bitcoin` | Tightly related fact tables (blocks, transactions, inputs, outputs). Tests cross-table foreign-key surfacing. |
