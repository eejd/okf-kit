---
type: Roadmap
title: Backlog (deferred findings)
description: Deferred v0.1 findings (adversarial + security review) with rationale
  — design calls, spec-defensible behavior, security residuals, spec alignment.
---
# Overview

Deferred findings from the v0.1 adversarial + security review, with rationale. Each entry is a conscious v0.1 deferral, not an oversight — kept here so nothing is silently lost. (This concept replaces the former `docs/backlog.md`.)

# Design calls (decide before implementing)

- **`okf index regen` overwrites hand-authored `index.md` body.** The generator regenerates the full body. v0.1 mitigation: documented caveat — avoid running regen on a root you've hand-curated, or back it up (see [Authoring](/guides/authoring.md)). Future: a managed region marker or `--force`.
- **MCP resources enumerated at startup** (snapshot), so concepts authored after `okf-mcp` starts aren't addressable as `okf://` resources without a restart. A resource template is blocked in v0.1 by FastMCP's URI-template matching of multi-segment concept ids. See [okf:// scheme](/interfaces/okf-uri-scheme.md).

# Spec-defensible current behavior

- **Unclosed frontmatter** (`---` with no close) is "no valid frontmatter" → graceful fallback (REQ-CONS-02), not an error. A stricter SPEC §9 reading would flag it; deferred.
- **`read_concept(depth=0)` returns the raw file; `depth>0` a structured concatenation** with headers — inherent (one vs many), documented in [progressive context](/architecture/progressive-context.md).
- **Exact-title search boost** is full-string, case-insensitive equality only; partial matches get weighted-tf scoring. Acceptable for v0.1.

# Security residuals (document, harden in CI)

- **YAML alias-bomb (billion-laughs)** survives `yaml.safe_load`. The 8 MB per-file cap bounds file size, not alias expansion. Mitigation: a custom loader disabling aliases, or a node-count cap.
- **Windows path separators** (`\`) aren't treated as separators (v0.1 targets Linux stdio). If Windows is supported, also split on `os.altsep` and reject `\` / NUL.
- `BundleRegistry.get` lists registered bundle names in its `KeyError` (minor local info disclosure) — drop the listing.

# Spec alignment

Closed: §5 cross-linking — graph edges + progressive context now follow BOTH relative and absolute (bundle-relative) links (absolute is spec-recommended). Intentionally kept: the `invalid-cid` warning (OKF defines no filename regex; ours enables [path containment](/architecture/path-containment.md)), non-mapping YAML → error (stricter, defensible), and nested `index.md` frontmatter → `info` (forward-compat sub-bundle marker).