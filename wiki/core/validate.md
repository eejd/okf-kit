---
type: Module
title: core/validate — conformance
description: validate_bundle walks a bundle, classifies every .md into errors/warnings/info,
  and returns a Report — the only judge of conformance.
---
# Overview

`okf_kit/core/validate.py` implements OKF v0.1 conformance (SPEC §9; REQ-BM-04, REQ-API-01..04). It walks every `.md` under the root via the safe enumerator, parses each, and classifies findings into three severities. It is **the only judge** — the permissive parser never raises; this module turns parse diagnostics into conformance findings. See [Conformance](/format/conformance.md) for the policy.

# Definition

`validate_bundle(root)` returns a `Report(errors, warnings, info)` with a `conformant` property (`not errors`). Per concept:

- **errors** — `frontmatter-missing`, `frontmatter-invalid`, `type-empty`.
- **warnings** — missing recommended `title` / `description`, `invalid-cid` (violates the segment regex → unaddressable), `broken-link`.
- **info** — extension frontmatter keys, `log-frontmatter`, `nested-index-frontmatter` (forward-compat sub-bundle marker).

Reserved files get special handling: a root `index.md` is checked only for `okf_version` (extra keys are info); a nested `index.md` carrying frontmatter is info, not error. After the walk, `_check_okf_version` reports a missing/mismatched `okf_version` as info, and a zero-concept bundle as `empty-bundle` info.

# API

`Report.to_dict()` serializes to `{conformant, errors, warnings, info}` — the exact shape the MCP `validate` tool returns and the CLI `--json` flag prints. Each `Finding` carries `severity`, `code`, `message`, `cid`, `path`. Broken links come from [links module](/core/links.md); parsing from [parse module](/core/parse.md).