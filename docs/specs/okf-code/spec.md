# Spec: OKF code indexing

- **Status:** Shipped
- **Owner:** okf maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** RFC-0002
- **Brief:** none
- **Contract:** none
- **Shape:** integration

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.

## Objective

Ship the first RFC-0002 implementation slice: an optional Tree-sitter-backed
`okf code index` workflow that turns source files into normal OKF
`CodeModule` concepts, plus an `okf-code` skill that tells agents how to use
those concepts for documentation, code finding, code-logic search, and
impact-analysis groundwork. A user with `okf-kit[treesitter]` installed can
index Python, Java, Scala, Rust, Go, Kotlin, Perl, C#, PHP, TypeScript,
JavaScript, and HTML repositories into an OKF bundle, run existing `okf search` and
`okf read --depth N` against the generated concepts, and refresh generated
facts without hand-reading every source file.

## Boundaries

### Always do

- Keep source-code parsing outside `okf_kit.core`; the pure OKF Markdown core
  remains deterministic and source-language agnostic.
- Generate standard OKF Markdown concepts that existing validate/search/read,
  MCP, and web surfaces can consume.
- Gate Tree-sitter dependencies behind an optional `treesitter` extra and make
  missing dependency errors actionable.
- Preserve hand-authored content by writing generated sections inside managed
  markers only.
- Organize code indexing as an `okf_kit.code` package with focused modules for
  discovery, pathing, rendering, managed-section merging, indexing, and
  Tree-sitter language adapters.
- Support Python, Java, Scala, Rust, Go, Kotlin, Perl, C#, PHP, TypeScript,
  JavaScript, and HTML through `tree-sitter-language-pack`.

### Ask first

- Adding semantic providers such as LSP, SCIP, typecheckers, or framework
  analyzers.
- Adding `okf code refresh`, `okf code explain`, or `okf code impact` as
  mechanical CLI commands instead of skill workflows.
- Adding plugin packaging, MCP configuration, subagents, or hooks.
- Adding languages beyond Python, Java, Scala, Rust, Go, Kotlin, Perl, C#, PHP,
  TypeScript, JavaScript, and HTML.

### Never do

- Do not require Tree-sitter for normal OKF bundle use.
- Do not store raw ASTs as OKF concepts.
- Do not add a new context primitive beyond `read_concept(depth=N)`.
- Do not overwrite files outside the selected OKF bundle.
- Do not claim syntax-derived impact candidates are complete semantic proof.

## Testing Strategy

- Parser extraction: TDD. Unit tests cover Python symbol extraction,
  dependency-missing errors, deterministic symbol ordering, source-range
  metadata, and representative symbols across the supported language set.
- OKF generation: TDD. Unit tests cover generated `CodeModule` concept shape,
  managed-section replacement, path containment, and preservation of narrative
  content outside generated markers.
- CLI surface: subprocess tests. `okf code index --help` and a small fixture
  repository prove the command writes a valid bundle and can be searched with
  existing OKF commands.
- Packaging and skill assets: goal-based plus tests. Package assets include
  `okf-code`, the optional extra is declared, and docs mention the opt-in
  dependency without implying Tree-sitter is required for base OKF.
- Gates: run `uv run ruff check .`, `uv run mypy okf-kit/okf_kit`, and
  `uv run pytest`.

## Acceptance Criteria

- [x] `pyproject.toml` defines a `treesitter` optional dependency group for the
  parser dependencies, while base `okf-kit` still imports without Tree-sitter
  installed.
- [x] `okf code index <repo> <bundle>` exists and prints actionable help,
  including supported languages and the optional `treesitter` dependency.
- [x] With Tree-sitter dependencies available, indexing supported source trees
  writes or updates valid OKF `CodeModule` concepts containing frontmatter,
  `# Overview`, generated `# Symbols`, generated `# Relationships`, generated
  `# Impact notes`, and `# Citations`.
- [x] Generated concepts preserve non-generated narrative body content across a
  second index run while replacing only managed generated sections.
- [x] Generated concepts include enough searchable text for existing
  `okf search` to find modules by source path and symbols by name.
- [x] Generated concepts render resolvable local source imports as Markdown
  links to other generated `CodeModule` concepts, so `okf read --depth 1` can
  traverse code relationships where the syntax-only resolver has evidence.
- [x] Indexing fails before writing generated code concepts when distinct
  source paths normalize to the same OKF concept id.
- [x] The generated bundle validates with `okf validate`.
- [x] Missing optional parser dependencies produce a clear CLI error telling the
  user to install `okf-kit[treesitter]`.
- [x] Packaged `okf-code/SKILL.md` explains the code indexing workflow and tells
  agents to use existing `okf search` / `okf read --depth N` for code
  documentation, code search, and impact-analysis groundwork.
- [x] README and wiki docs mention the first-slice scope without claiming
  semantic impact analysis, plugin packaging, or new MCP tools have shipped.
- [x] Existing gates pass: `uv run ruff check .`, `uv run mypy okf-kit/okf_kit`,
  and `uv run pytest`.

## Assumptions

- Technical: project runtime is Python 3.12+ with Hatchling and console scripts
  `okf` / `okf-mcp` (source: pyproject.toml).
- Technical: current CLI already has `init/new/validate/search/read/index/serve/agent`,
  so `code` is a sibling namespace and must not disturb existing commands
  (source: okf-kit/okf_kit/cli.py).
- Technical: RFC-0002 recommends `okf-kit[treesitter]`, Tree-sitter hybrid
  indexing, an `okf-code` skill, and manifest-backed refresh
  (source: docs/rfc/0002-okf-for-codebases.md).
- Product: first implementation should support documenting and finding code,
  code-logic search, and impact-analysis groundwork (source: user confirmation
  2026-06-18).
- Process: RFC-0002 is still Draft, but the user explicitly asked to create a
  branch and implement the first slice (source: user confirmation 2026-06-18).
- Process: `docs/CONVENTIONS.md` and `docs/CHARTER.md` are absent in this
  checkout; prior spec shape comes from
  `docs/specs/okf-agent-installer/spec.md` (source: targeted repo check).
