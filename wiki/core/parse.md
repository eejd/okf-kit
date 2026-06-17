---
type: Module
title: core/parse — frontmatter splitting
description: split_frontmatter, parse_concept, serialize_concept — permissive frontmatter
  handling that never raises and round-trips cleanly.
---
# Overview

`okf_kit/core/parse.py` turns text into `Concept` objects and back. Its defining rule, from SPEC §4.1 / REQ-CONS-01..04: **never raise on malformed input.** A missing block degrades to an empty-mapping concept whose whole text is the body; a present-but-invalid block (non-mapping or unparseable YAML) records a `frontmatter_error` so the validator can report it.

# Definition

- **`split_frontmatter(text)`** — a valid block opens with `---` on the very first line (no leading whitespace, no BOM) and closes with a later line of exactly `---`. Returns `FrontmatterResult(data, body, present, error)`. An empty block is `present=True, data={}`. Parsing uses `yaml.safe_load` (no arbitrary object instantiation — REQ-CONS-01).
- **`parse_concept(path, root)`** — stat the file (size-capped by `_MAX_CONCEPT_BYTES`), read UTF-8, split, and build a `Concept` with its `cid` derived from the path. A stat failure or oversize file yields a concept carrying a `frontmatter_error` rather than throwing.
- **`serialize_concept(concept)`** — the inverse: `yaml.safe_dump` with `sort_keys=False` (order preserved) + body. A concept with no frontmatter serializes body-only, enabling lossless round-trips.

# Examples

The "present but empty" vs "absent" distinction is what lets the validator emit `type-empty` only when a block exists. The dataclass that parse produces is [Concept](/core/model.md); the validator that consumes its diagnostics is [validate module](/core/validate.md).