---
type: Architecture
title: Permissive parsing
description: The parser never raises on malformed input — it degrades gracefully and
  records a diagnostic; the validator is the single judge of conformance.
---
# Overview

A core OKF principle is **permissive consumption**: a consumer MUST NOT reject a document for missing optional fields, unknown types, extension keys, or broken links. `okf-kit` encodes this as a hard split — the **parser** is permissive and never raises; the **validator** is the one and only judge of conformance. Nothing in the read path throws on bad shape; it produces a degraded `Concept` plus a diagnostic, and lets [Conformance](/format/conformance.md) decide.

# Definition

`split_frontmatter` / `parse_concept` degrade gracefully at every failure mode:

- No `---` on line 1 (or a leading BOM) → no frontmatter; the whole file is the body, `frontmatter_present=False`.
- A present-but-empty block → empty mapping, present.
- Unparseable YAML, or a non-mapping (e.g. a bare list) → empty mapping with a `frontmatter_error` string. The **validator** turns a present-but-invalid block into a conformance **error** (REQ-CONS-03); a merely-absent block is its own error (`frontmatter-missing`).

Unknown frontmatter keys and unknown `type` values are **preserved**, never rejected — round-tripping keeps everything (REQ-CONS-04). A `_MAX_CONCEPT_BYTES` guard caps pathological files (a local-tool belt-and-suspenders DoS guard, not a hard SLA).

# Examples

This is why both the CLI and MCP are so thin: they call `parse_concept` and `validate_bundle` and present the result. The CLI prints the report and maps `conformant` to exit code; the MCP `validate` tool returns it as JSON. Details in [parse module](/core/parse.md) and [validate module](/core/validate.md).