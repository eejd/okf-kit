---
type: Module
title: core/index — index.md regeneration
description: regenerate_indexes writes a type-grouped, per-directory index.md for
  every directory containing a concept; root index preserves okf_version.
---
# Overview

`okf_kit/core/index.py` regenerates the reserved `index.md` files (REQ-BM-05, REQ-PROD-05, SPEC §6). For every directory that contains a concept anywhere in its subtree, it writes a body-only listing that groups children by `type` (title + description) and links subdirectories. Only the root `index.md` may keep frontmatter (`okf_version`); non-root indexes are body-only. See [Reserved files](/format/reserved-files.md).

> Note: this concept's id is `core/index-regen`, not `core/index`. The literal id `core/index` maps to the reserved filename `index.md`, which the validator treats as a reserved directory listing (excluded from the graph) — so any module named `index.py` must be documented under a non-reserved cid.

# Definition

`regenerate_indexes(root)`:

1. Enumerate concepts (reserved excluded) and compute the set of target directories — every ancestor up to the root of each concept's directory.
2. For each target directory, render `_render_index`: root gets its existing `okf_version` re-emitted in frontmatter; then a `# <Type>` section per type with `* [title](file.md) - description` lines (sorted by cid); then a `# Subdirectories` section linking child `index.md` files.
3. Overwrite each `index.md`.

`_existing_okf_version` reads any prior root index so regeneration is non-destructive toward the version declaration. Missing optional `title` / `description` fall back to the cid tail / nothing.

# Examples

Output for a root with one Table and a `metrics/` subdir:

    # Table
    * [users](users.md) - User accounts.
    # Subdirectories
    * [metrics](metrics/index.md)

Invoked by the CLI `okf index regen` (there is no MCP tool for index regen — it is a generated artifact, not authored knowledge).