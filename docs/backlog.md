# OKF backlog

Deferred findings from the v0.1 adversarial + security review, with rationale.
Each is a conscious v0.1 deferral, not an oversight.

## Design calls (need a decision before implementing)

- **`okf index regen` overwrites hand-authored `index.md` body.** The generator
  regenerates the full body (it's a generator). A hand-authored root `index.md`
  with intro prose will be overwritten. v0.1 mitigation: documented caveat (see
  `docs/authoring.md`); avoid running regen on a root you've hand-curated, or
  back it up. Future: a managed region (`<!-- okf:index -->` marker) or
  `--force`, and idempotent re-runs.
- **MCP resources are enumerated at startup** (not a template), so concepts
  authored after `okf-mcp` starts aren't addressable as `okf://` resources
  without a restart. A resource template (`okf://{bundle}/concepts/{cid}.md`)
  is blocked in v0.1 by FastMCP's URI-template matching of multi-segment
  (slash-containing) concept ids. Documented in `docs/okf-uri-scheme.md`.

## Spec-defensible current behavior (intentional, not bugs)

- **Unclosed frontmatter** (`---` with no closing delimiter) is treated as
  "no valid frontmatter" → graceful fallback (REQ-CONS-02), not an error. A
  stricter reading (SPEC §9 "malformed = error") would flag it; deferred.
- **`read_concept(depth=0)` returns the raw file; `depth>0` returns a structured
  concatenation** with headers. This is inherent (one concept vs many) and
  documented in the `read_concept` docstring + `docs/progressive-context.md`.
- **`token_budget` governs the `depth>0` neighborhood**, not the single
  `depth=0` concept (which is returned in full). Documented.
- **Exact-title search boost** is full-string, case-insensitive equality only;
  partial/term-reorder matches get weighted-tf scoring (no boost). Acceptable
  for v0.1; a smarter "all terms in title" signal is a future ranker change.

## Performance (v0.2/v0.4 — REQ-NF-01)

- `read_concept(depth>0)`, `validate_bundle`, `build_index` each walk + parse
  the whole bundle. No caching/sidecar index yet. Fine for small bundles;
  matters at 10K+ concepts (sidecar index + memoized adjacency, design §13 v0.4).
- `regenerate_indexes` is a two-pass O(concepts × depth) walk; a single
  group-by-parent pass is cleaner.

## Security residuals (document, harden in CI)

- **YAML alias-bomb (billion-laughs)** survives `yaml.safe_load` (anchors/
  aliases expand). The 8 MB per-file cap (`parse._MAX_CONCEPT_BYTES`) bounds
  *file* size but not alias expansion of a small file. Mitigation: a custom
  loader that disables aliases, or node-count cap. Recommend wiring in CI.
- **Windows path separators** (`\`) are not treated as separators (v0.1 targets
  Linux stdio). If Windows is ever supported, also split on `os.altsep` and
  reject `\`/NUL in segments.
- `BundleRegistry.get` lists registered bundle names in its `KeyError` message
  (minor info disclosure to a local client). Drop the listing.
- `okf init --okf-version` accepts any string (the validator later flags
  non-`0.1`). Cosmetic.

## Supply chain (not source-reviewed)

- Run `pip-audit` / Dependabot over `mcp`, `pyyaml`, transitive deps in CI.
- ReDoS of `_LINK_RE` not formally verified (it's linear; low risk).
