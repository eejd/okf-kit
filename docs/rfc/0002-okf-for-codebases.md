# RFC-0002: OKF for codebases

- **Status:** Draft
- **Author:** okf maintainers
- **Approver:** user
- **Date opened:** 2026-06-17
- **Date closed:**
- **Related:** RFC-0001; README.md; AGENTS.md; wiki/architecture/progressive-context.md; wiki/project/backlog.md

## The ask

**Recommendation (BLUF):** approve an optional Tree-sitter-backed codebase
extension for OKF: `okf-kit[treesitter]`, an `okf code ...` CLI namespace, and
an `okf-code` agent skill. The extension should generate and refresh normal OKF
Markdown concepts from source code so agents can document, find, search, and
reason about implementation impact without reading a whole repository file by
file.

**Why now:** OKF works well for small repositories and hand-authored knowledge
bases, and the current `okf-author` skill already has a repository
implementation-wiki workflow. The slow part is mechanical code discovery:
agents must inventory files, entry points, symbols, imports, and likely impact
paths by reading text directly. The question is whether OKF should keep that
manual or add a parser-backed producer layer that turns code structure into
progressive OKF context.

**Decisions requested:**

1. Parser packaging: recommend `okf-kit[treesitter]` as the first optional code
   parser extra. Decide by RFC acceptance; default yes.
2. Indexing model: recommend Tree-sitter-first hybrid indexing, with syntax
   extraction first and optional semantic enrichment later from LSP/SCIP or
   language-specific tools. Decide by RFC acceptance; default yes.
3. Concept granularity: recommend generated OKF code concepts at
   module/component level with generated symbol inventories, not raw AST dumps
   and not one concept per function by default. Decide by RFC acceptance;
   default yes.
4. Agent workflow: recommend a new `okf-code` skill for codebase documentation,
   code search, and impact analysis. Decide by RFC acceptance; default yes.
5. Refresh model: recommend manifest-backed partial regeneration so generated
   code facts can refresh without overwriting hand-authored narrative sections.
   Decide by RFC acceptance; default yes.

## Problem & goals

OKF's core model is intentionally simple: a bundle is Markdown concepts plus
links. That simplicity is still right for codebases, but codebases have a
mechanical discovery layer that prose knowledge bases do not. A source tree
already contains symbols, imports, routes, tests, and file boundaries. If an
agent must rediscover those facts by opening files one by one, building the
knowledge base is slow and often shallow.

The gap is not "OKF cannot document code." The current `okf-author` skill
already tells agents to build implementation wikis as OKF bundles. The gap is
that OKF does not yet provide a fast producer that can extract source-code facts
and give the agent a cheap, searchable map before narrative documentation is
written.

**Goals:**

- Make OKF useful for medium and large codebases without requiring agents to
  read every source file up front.
- Produce normal OKF bundles that existing `search`, `read`, `validate`, MCP,
  and browser workflows can consume.
- Support documentation, code finding, code-logic search, and impact analysis.
- Keep `okf_kit.core` pure: code parsing is producer/indexer behavior, not a
  change to OKF conformance or Markdown parsing.
- Start with syntax-level facts from Tree-sitter, then allow semantic enrichment
  where a language tool can provide better references, types, or call edges.

**Non-goals:**

- Do not turn OKF into a hosted code search engine.
- Do not store raw ASTs as OKF concepts.
- Do not require Tree-sitter for normal OKF bundle use.
- Do not promise perfect semantic impact analysis in the first slice.
- Do not add another context primitive that competes with
  `read_concept(depth=N)`.
- Do not overwrite hand-authored implementation notes during refresh.

## Proposal

Add an optional code extension shipped as a Python extra:

```bash
pip install "okf-kit[treesitter]"
uv sync --extra treesitter
```

The extra should install the parser dependencies needed by the code producer,
for example `tree-sitter` plus a maintained parser bundle such as
`tree-sitter-language-pack`. The base `okf-kit` install remains lightweight and
continues to support normal Markdown bundles with no parser dependency.

Add a CLI namespace outside the existing bundle commands:

```bash
okf code index <repo> <bundle> [--languages python,typescript] [--update]
okf code refresh <bundle> [--repo <repo>]
okf code explain <bundle> <source-path-or-symbol>
okf code impact <bundle> <source-path-or-symbol>
```

The first implementation may ship only `index` and `refresh`; `explain` and
`impact` can be skill workflows over generated OKF concepts until their
mechanical contracts are specified. The important boundary is that the producer
writes OKF concepts, and existing OKF read/search/context behavior remains the
consumption path.

Generated concepts should use normal OKF frontmatter plus extension keys:

```yaml
---
type: CodeModule
title: okf_kit.core.search
description: Search index construction and weighted ranking.
resource: okf-kit/okf_kit/core/search.py
tags: [code, python, search]
source_path: okf-kit/okf_kit/core/search.py
language: python
source_hash: "..."
managed_by: okf-code
---
```

The body should be readable Markdown, not serialized parser output:

- `# Overview` for the module/component responsibility.
- `# Symbols` as a generated inventory of classes, functions, public methods,
  line ranges, and short signatures.
- `# Relationships` for imports, local references, routes, tests, or likely
  impact paths when extractable.
- `# Impact notes` for generated candidates plus hand-authored caveats.
- `# Citations` pointing back to source files and line ranges.

For granularity, default to one concept per meaningful module/component plus
generated inventories. Very large modules may split into child concepts, but
the default should avoid one concept per function because that explodes bundle
size and makes progressive context noisy.

For code search and impact analysis, the first slice should support:

- search by symbol, file path, tag, language, and module/component title;
- read a module/component concept at `depth=0`;
- expand to imported modules, callers/callees where known, tests, and related
  flows at `depth=1..N`;
- surface "impact candidates" as a ranked, evidence-backed list with source
  paths and why each candidate is related.

The impact model should be explicit about confidence:

- **syntax confidence** from Tree-sitter facts such as imports, definitions,
  exported names, route declarations, and test references;
- **semantic confidence** only when an enrichment provider proves definitions or
  references through LSP, SCIP, typecheckers, or language-specific analyzers;
- **narrative confidence** from hand-authored OKF concepts and links.

Add an `okf-code` skill rather than overloading `okf-author`. The skill should
tell agents to:

1. run or refresh `okf code index`;
2. use `okf search` and `okf read --depth N` over the generated bundle;
3. answer code-finding and impact-analysis questions with cited concepts and
   source paths;
4. update hand-authored narrative sections when code facts reveal missing
   architecture context;
5. validate and regenerate indexes.

Packaging can later become a Codex or Claude Code plugin that bundles the
`okf-code` skill and optional MCP configuration. RFC-0002 approves the workflow
shape; a follow-on spec should decide the exact command contracts and packaged
skill text.

## Options considered

The primary option space is MECE along where codebase knowledge is produced and
owned.

| Option | Prior art | Trade-offs |
|---|---|---|
| Do nothing | Current `okf-author` can manually create implementation wikis. | No dependency or surface change, but agents stay slow on repo inventory and impact analysis. |
| Skill-only workflow | RFC-0001 established installable skills for OKF workflows. | Improves agent behavior but still leaves mechanical symbol extraction to manual file reads. |
| Add code parsing to `okf_kit.core` | Existing core owns parse/search/context for OKF Markdown. | Rejected: this pollutes pure OKF bundle logic with source-language concerns. |
| Optional `okf-kit[treesitter]` producer | Python extras are a standard way to keep optional dependencies out of base installs; Tree-sitter is designed for robust syntax trees. | Recommended: opt-in dependency, fast syntax extraction, normal OKF output. |
| Full code-intelligence platform | CodeQL, LSP, and SCIP show richer semantic indexing models. | Too broad for OKF's scope; useful as future enrichment, not the first OKF codebase feature. |

### `okf-kit[treesitter]` pros and cons

**Pros:**

- Keeps the base install small and preserves normal OKF usage without parser
  dependencies.
- Makes codebase support discoverable through normal Python packaging.
- Gives the CLI a clear feature gate: commands can explain "install
  `okf-kit[treesitter]`" when parser dependencies are missing.
- Fits the existing project style: optional capability outside `core`, with
  tests around the presentation and producer layer.
- Lets OKF support many languages without hand-writing per-language regex
  scanners.

**Cons:**

- Adds dependency and packaging complexity, especially around native parser
  wheels and supported Python/platform combinations.
- Tree-sitter gives syntax, not full semantics. It will not automatically know
  all call targets, dynamic imports, framework conventions, or type-resolved
  references.
- Parser bundles can lag language changes or differ in API shape. The spike
  found wrapper differences between upstream `py-tree-sitter` examples and the
  selected language-pack wrapper.
- Generated facts can drift from source unless refresh is cheap and manifest
  ownership is strict.
- Users may expect "impact analysis" to be exact. The product must label
  confidence and distinguish syntax-derived candidates from semantic proof.

The recommendation is still `okf-kit[treesitter]`, with a clear non-promise:
the first version produces fast, useful, evidence-backed code maps; it does not
claim whole-program semantic correctness.

## Risks & what would make this wrong

**Pre-mortem:** this ships and fails because generated concepts are too noisy,
Tree-sitter packaging is brittle, generated sections overwrite useful
hand-authored documentation, or users treat syntax-derived impact candidates as
complete semantic proof. Mitigations: default to module/component granularity,
hide parser dependencies behind the optional extra, use a manifest plus managed
regions, and label impact confidence in every generated answer.

**Key assumptions:**

- Tree-sitter extraction is fast enough to make codebase indexing materially
  cheaper than manual agent reading. This is false if parser setup dominates
  runtime or language coverage is poor for common OKF users.
- Module/component concepts plus symbol inventories are the right default
  granularity. This is false if users primarily ask about individual functions
  and need symbol-level concepts.
- Existing OKF `search` and `read_concept(depth=N)` remain sufficient for
  consuming code concepts. This is false if code impact queries require a new
  graph traversal primitive that cannot be represented through Markdown links.
- Optional semantic enrichment can wait. This is false if syntax-only impact
  candidates are too noisy to be trusted.

**Drawbacks:**

- The CLI grows a second producer namespace beyond human-authored knowledge
  bundles.
- The project takes on parser dependency maintenance and language support
  expectations.
- Generated OKF bundles can become large; indexing must avoid concept explosion.
- Refresh semantics require careful ownership boundaries so generated facts and
  human notes can coexist.

## Evidence & prior art

**Spike / de-risk result:** using `uv run --with tree-sitter --with
tree-sitter-language-pack`, a small script parsed the repository's Python source
under `okf-kit/` and extracted `305` class/function symbols from `28` files in
`63.2ms`. The spike had to adapt to the selected wrapper's API shape
(`kind`, `child_count()`, `ByteRange.start/end`) rather than upstream
`py-tree-sitter` examples (`type`, `children`, `text`), so the implementation
must wrap parser APIs behind OKF-owned adapters and tests. The result supports
Tree-sitter as a fast syntax layer; it does not prove semantic impact analysis.

**Repo precedent:**

- `AGENTS.md` says v0.1 is build/use a KB, while producer/import and full pack
  work are deferred.
- `AGENTS.md`, `wiki/architecture/progressive-context.md`, and
  `docs/specs/okf-agent-installer/spec.md` all say `read_concept(depth=N)` is
  the one context primitive; RFC-0002 keeps that boundary.
- `README.md` and the packaged `okf-author` skill already mention
  implementation wikis for code repositories, but the workflow is manual.
- RFC-0001 explicitly deferred `okf-import` / `okf-producer`; code indexing is
  the first concrete producer candidate.
- `wiki/conventions/build-and-gates.md` says `cli` and `mcp` are presentation
  layers and shared logic belongs in core. RFC-0002 follows the spirit but keeps
  parser-specific logic out of `okf_kit.core` because it is not OKF Markdown
  bundle logic.
- `docs/CHARTER.md`, `docs/CONVENTIONS.md`, `docs/adr/`, and
  `docs/architecture/` are absent in this checkout, so there is no additional
  local governance precedent to cite.

**External prior art:**

- Tree-sitter is a parser generator and incremental parsing library for source
  code: https://tree-sitter.github.io/tree-sitter/
- The official Python bindings expose parser, tree, node, field, and query APIs
  suitable for symbol extraction: https://tree-sitter.github.io/py-tree-sitter/
- Tree-sitter queries provide a source-language-aware way to match syntax nodes:
  https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html
- `tree-sitter-language-pack` packages many Tree-sitter grammars for Python:
  https://github.com/kreuzberg-dev/tree-sitter-language-pack
- ast-grep is prior art for structural search on top of Tree-sitter:
  https://ast-grep.github.io/
- LSP document/workspace symbols and semantic tokens show a standard semantic
  tool boundary beyond syntax parsing:
  https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/
- SCIP is prior art for language-independent code-intelligence indexes:
  https://scip-code.org/
- CodeQL is prior art for a heavier code database approach:
  https://codeql.github.com/docs/
- Codex plugins can bundle reusable skills and MCP configuration, which is a
  plausible later distribution form for `okf-code`:
  https://developers.openai.com/codex/plugins

## Experiment / validation

Before implementation is accepted, run a pilot on at least two repositories:

- **Hypothesis:** a Tree-sitter-backed `okf code index` produces a searchable
  OKF code map faster and with better source grounding than the current manual
  `okf-author` repository-wiki workflow.
- **What we measure:** indexing time, number of generated module/component
  concepts, symbol extraction accuracy on sampled files, search success for
  known symbols/logic, impact-candidate precision on known changes, and whether
  `okf read --depth 1` stays useful under token budgets.
- **Success criteria:** the generated bundle validates, common code-finding
  questions can be answered from OKF concepts with source citations, and impact
  candidates are useful enough when labeled as syntax/semantic/narrative
  confidence.
- **Failure criteria:** generated output is mostly noise, parser packaging
  blocks normal install paths, or impact candidates are so broad that agents
  still need to read the repo manually from scratch.

## Open questions

None for the RFC direction. The follow-on spec should decide exact command
arguments, generated concept ids, supported languages for the first release,
and the managed-region marker format.

## Follow-on artifacts

- Spec: `docs/specs/okf-code/` for `okf-kit[treesitter]`, `okf code index`,
  refresh semantics, generated concept shape, and verification.
- Skill: packaged `okf-code/SKILL.md` for codebase documentation, code search,
  and impact-analysis workflows.
- Optional ADR: record the boundary that source-code parsing is producer logic
  outside `okf_kit.core`.
- Documentation updates: README, `wiki/interfaces/okf-cli.md`,
  `wiki/guides/authoring.md`, and `wiki/reference/tools.md` after the spec
  lands.
