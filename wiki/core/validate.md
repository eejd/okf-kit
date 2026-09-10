---
type: Module
title: core/validate — conformance
description: validate_bundle walks a bundle, classifies every .md into errors/warnings/info,
  and returns a Report — the only judge of conformance.
---
# Overview

`okf_kit/core/validate.py` implements OKF v0.2 conformance (SPEC §11; REQ-BM-04, REQ-API-01..04). It walks every `.md` under the root via the safe enumerator, parses each, and classifies findings into three severities. It is **the only judge** — the permissive parser never raises; this module turns parse diagnostics into conformance findings. See [Conformance](/format/conformance.md) for the policy.

# Definition

`validate_bundle(root)` returns a `Report(errors, warnings, info)` with a `conformant` property (`not errors`). Per concept:

- **errors** — `frontmatter-missing`, `frontmatter-invalid`, `type-empty`.
- **warnings** — missing recommended `title` / `description`, `invalid-cid` (violates the segment regex → unaddressable), `broken-link`.
- **info** — extension frontmatter keys, `log-frontmatter`, `nested-index-frontmatter` (forward-compat sub-bundle marker).

Reserved files get special handling: a root `index.md` is checked only for `okf_version` (extra keys are info); a nested `index.md` carrying frontmatter is info, not error. After the walk, `_check_okf_version` reports a missing/mismatched `okf_version` as info, and a zero-concept bundle as `empty-bundle` info.

# Hive publication profile

`validate_bundle(root, profile="hive")` additionally checks each concept against the
versioned `hive-publication-profile.v1.schema.json` copied byte-for-byte from the canonical
knowledge-hive contract. It requires the controlled type, title, publication/governance/
implementation/applicability axes, hive, owner repository, subject identity, authority, and
an origin with an exact 40-character lowercase Git commit and `sha256:` digest. Typed
relations are top-level lists of unique, non-empty targets; the legacy nested `relations`
mapping is rejected.

This local profile is intentionally fail closed. It cannot verify an origin against the
knowledge-hive migration manifest, prove unique current authority across every registered
bundle, or establish cross-bundle graph connectivity. It therefore always returns the
`hive-external-publication-required` publication error. The knowledge-hive portfolio
validator must clear those checks before publication; okf-kit never claims that concept-level
validation alone makes a bundle publishable.

# API

`Report.to_dict()` serializes to `{conformant, publishable, profile, errors,
publication_errors, warnings, info}` — the exact shape the MCP `validate` tool returns and
the CLI `--json` flag prints. Generic OKF conformance remains independent of publication
profile errors. Each `Finding` carries `severity`, `code`, `message`, `cid`, `path`.
Broken links come from [links module](/core/links.md); parsing from
[parse module](/core/parse.md).
