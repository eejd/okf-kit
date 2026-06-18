# Plan: OKF code indexing

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done

> **Plan contract:** this is the implementation strategy. Unlike the spec, this
> document is allowed to change as you learn. When it changes substantially,
> note why in the changelog at the bottom.

## Approach

Add an `okf_kit.code` package outside `okf_kit.core`, backed by optional
Tree-sitter language adapters that import parser dependencies only inside the
code-indexing path. The producer scans supported files under a repository,
extracts module-level symbols and imports, and writes deterministic
`CodeModule` concepts into an OKF bundle under managed generated sections. Wire
that producer through `okf code index`, install the packaged `okf-code` skill
asset with the other OKF skills, and update docs to frame this as syntax
indexing rather than complete semantic impact analysis.

Tempted to add `refresh`, `explain`, and `impact` commands now; declining
because the RFC explicitly lets those remain skill workflows until their
contracts are specified. Tempted to generate one concept per symbol; declining
because RFC-0002 recommends module/component concepts with symbol inventories.

## Constraints

- RFC-0002 constrains this to optional Tree-sitter-backed code indexing.
- `okf_kit.core` remains pure and must not import Tree-sitter.
- Normal OKF bundle commands must keep working without the `treesitter` extra.
- Generated files must pass existing OKF validation.
- First implementation supports Python, Java, Scala, Rust, Go, Kotlin, Perl,
  C#, PHP, TypeScript, JavaScript, and HTML through
  `tree-sitter-language-pack`.

## Construction tests

**Integration tests:** subprocess tests for `okf code index --help`, indexing a
small fixture repository, validating the generated bundle, searching for a
generated symbol, and exercising representative files across the supported
language set.
**Manual verification:** none.

## Design (LLD)

### Interfaces & contracts

Public CLI surface:

```bash
okf code index <repo> <bundle> [--language python] [--language typescript] [--update]
```

Exit code `0` means indexing completed. Exit code `2` means usage, missing
optional dependency, unsupported language, path, or IO errors. Without
`--language`, it indexes all supported languages. Re-running refreshes existing
generated concepts by default; `--update` is accepted for compatibility. The
command prints a short summary with the number of written or updated concepts.

### Data & schema

Generated concepts use `type: CodeModule`, `resource`, `tags`, and extension
frontmatter keys: `source_path`, `language`, `source_hash`, and `managed_by`.
Concept ids live under `code/<source-path-including-extension>`, with path
segments normalized to OKF-safe characters. Preserving source extensions avoids
collisions in polyglot repositories such as `src/app.py`, `src/app.ts`, and
`src/app.js`. The body is normal Markdown with managed generated sections
bounded by stable HTML comments:

```markdown
<!-- okf-code:start -->
...
<!-- okf-code:end -->
```

Text outside those markers is preserved on update.

### Component / module decomposition

- `okf_kit.code.model`: producer dataclasses.
- `okf_kit.code.discovery`: repository walking and language selection.
- `okf_kit.code.paths`: source path to concept-id mapping and containment.
- `okf_kit.code.managed`: generated-section merge/preservation.
- `okf_kit.code.render`: `CodeModule` Markdown rendering.
- `okf_kit.code.indexer`: indexing orchestration and extraction entry points.
- `okf_kit.code.treesitter.runtime`: lazy `tree-sitter-language-pack` wrapper.
- `okf_kit.code.treesitter.languages`: supported language adapters.
- `okf_kit.cli`: `code index` presentation layer only.
- `okf_kit/agent_assets/skills/okf-code/SKILL.md`: agent workflow text.
- Tests under `okf-kit/tests/` cover producer logic, CLI behavior, package
  assets, and docs.

### Failure, edge cases & resilience

Missing Tree-sitter dependencies raise a clear `ValueError` with installation
instructions. Repository and bundle paths are resolved before use; indexing
skips hidden directories, virtual environments, `__pycache__`, and the target
bundle when it lives inside the repository. Generated writes use existing OKF
concept creation/path containment helpers where possible and direct file writes
only after normalized concept ids are resolved inside the bundle. Syntax errors
produce degraded module concepts with any symbols Tree-sitter can recover,
rather than aborting the whole index.
Distinct source paths that normalize to the same `code/...` concept id fail
before generated concept writes begin. Resolvable local imports are rendered as
Markdown links to generated `CodeModule` concepts; unresolved imports remain
plain text because syntax-only extraction should not invent graph edges.

### Dependencies & integration

`pyproject.toml` declares a `treesitter` optional dependency group containing
`tree-sitter` and `tree-sitter-language-pack`. Runtime imports stay local to
`okf_kit.code.treesitter` so `import okf_kit` and normal CLI commands do not
require the extra.

## Tasks

### T1: Optional parser dependency and skill asset are package-visible

**Depends on:** none

**Touches:** pyproject.toml, okf-kit/okf_kit/agent_assets/skills/okf-code/SKILL.md, okf-kit/tests/test_skill.py

**Tests:**
- TDD: package asset tests assert `okf-code` exists, has valid frontmatter, and
  mentions `okf code index`, `okf search`, `okf read --depth`, and impact
  analysis. Verifies AC 8.
- Goal-based: grep/check confirms `pyproject.toml` exposes a `treesitter`
  optional dependency group. Verifies AC 1.

**Approach:**
- Add the optional dependency group.
- Add the packaged `okf-code` skill beside existing skills.
- Extend the existing skill asset tests.

**Done when:** skill tests fail before the asset exists and pass after it is
packaged.

### T2: Source extraction produces deterministic code facts

**Depends on:** T1

**Touches:** okf-kit/okf_kit/code/, okf-kit/tests/test_code_index.py

**Tests:**
- TDD: extraction returns deterministic module facts with source path, hash,
  imports, classes, functions, and line ranges from a small Python fixture.
  Verifies ACs 3 and 5.
- TDD: representative fixtures for Python, Java, Scala, Rust, Go, Kotlin, Perl,
  C#, PHP, TypeScript, JavaScript, and HTML produce searchable symbols.
  Verifies ACs 2, 3, and 5.
- TDD: missing Tree-sitter modules raise an actionable error mentioning
  `okf-kit[treesitter]`. Verifies AC 7.

**Approach:**
- Add dataclasses for `CodeSymbol` and `CodeModule`.
- Add Tree-sitter language adapters using `tree-sitter-language-pack` only
  inside the extraction path.
- Sort facts deterministically by path, symbol kind, line, and name.

**Done when:** producer unit tests pass and no code under `okf_kit/core` imports
Tree-sitter.

### T3: Indexer writes valid managed OKF CodeModule concepts

**Depends on:** T2

**Touches:** okf-kit/okf_kit/code/, okf-kit/tests/test_code_index.py

**Tests:**
- TDD: indexing writes valid Markdown concepts with required frontmatter and
  generated Overview/Symbols/Relationships/Impact notes/Citations sections.
  Verifies AC 3.
- TDD: a second index run preserves text outside managed markers and replaces
  generated content inside markers. Verifies AC 4.
- TDD: generated bundle validates and generated symbol names are found by
  existing `search`. Verifies ACs 5 and 6.
- TDD: normalized path collisions fail before writing generated code concepts.
- TDD: a resolvable local import renders as an OKF Markdown link and appears
  in `read --depth 1` output.

**Approach:**
- Normalize source paths to `code/...` concept ids while preserving source
  extensions.
- Render managed generated Markdown from module facts.
- Preserve existing narrative outside generated markers on update.
- Reuse `init_bundle`, `parse_concept`, `serialize_concept`, and
  `validate_bundle` where they fit.

**Done when:** code-indexing unit tests pass and generated fixture bundles pass
OKF validation.

### T4: CLI exposes `okf code index`

**Depends on:** T3

**Touches:** okf-kit/okf_kit/cli.py, okf-kit/tests/test_cli.py

**Tests:**
- TDD/subprocess: `okf code index --help` shows repo, bundle, language, update,
  supported languages, and `okf-kit[treesitter]` wording. Verifies AC 2.
- TDD/subprocess: indexing a fixture repo writes concepts, validates the bundle,
  and search finds a generated symbol. Verifies ACs 2, 3, 5, and 6.
- TDD/subprocess: missing dependency error exits `2` with install guidance if
  the adapter reports missing parser packages. Verifies AC 7.

**Approach:**
- Add `code` parser namespace and `index` subcommand.
- Keep CLI thin; delegate indexing to `okf_kit.code.indexer.index_codebase`.
- Print a stable summary.

**Done when:** CLI tests pass and existing CLI behavior remains green.

### T5: Docs reflect first-slice scope and gates pass

**Depends on:** T1-T4

**Touches:** README.md, wiki/interfaces/okf-cli.md, wiki/guides/authoring.md, wiki/reference/tools.md, docs/specs/README.md

**Tests:**
- Goal-based: docs tests pass and docs mention `okf-kit[treesitter]`,
  `okf code index`, `okf-code`, supported language scope, and no shipped semantic
  impact command. Verifies AC 9.
- Goal-based: `uv run ruff check .`, `uv run mypy okf-kit/okf_kit`, and
  `uv run pytest`. Verifies AC 10.

**Approach:**
- Update README and wiki docs after CLI behavior is final.
- Add the spec to `docs/specs/README.md`.
- Mark acceptance criteria complete only after gates pass.

**Done when:** all gates pass and the spec status/ACs match the shipped slice.

## Rollout

This ships as an opt-in CLI/package feature. Users install the extra, run
`okf code index <repo> <bundle>`, then use existing OKF read/search tooling.
Rollback is deleting the generated `code/` concepts or restoring the bundle
from git.

## Risks

- Tree-sitter dependency wheels may not be available everywhere; mitigate by
  keeping the extra optional and producing a clear missing-dependency error.
- Syntax-only relationships may be overinterpreted as semantic impact proof;
  mitigate with explicit wording in generated Impact notes and docs.
- Concept ids derived from source paths may collide after normalization;
  mitigate with deterministic path normalization tests and source-path
  frontmatter.
- Generated content may overwrite user notes; mitigate with managed markers and
  preservation tests.

## Changelog

- 2026-06-18: initial plan from RFC-0002 and user implementation request.
- 2026-06-18: revised after review to replace the root-level `code_index`
  prototype with an `okf_kit.code` package and supported language adapters for
  Python, Java, Scala, Rust, Go, Kotlin, Perl, C#, PHP, TypeScript,
  JavaScript, and HTML.
- 2026-06-18: added Rust, Go, and PHP adapters; Perl was already present.
- 2026-06-18: added pre-write duplicate concept-id detection and resolvable
  local-import Markdown links for progressive depth reads.
