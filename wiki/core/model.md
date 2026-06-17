---
type: Module
title: core/model — Concept dataclass
description: The Concept dataclass — the in-memory representation of one OKF file
  (cid, path, frontmatter, body, reserved, diagnostics).
---
# Overview

`okf_kit/core/model.py` defines `Concept`, the single in-memory representation of one OKF Markdown file. It is a plain dataclass with no behavior — just the fields needed to round-trip a file and carry diagnostics. Because the on-disk format *is* the in-memory model (no translation layer), `Concept` deliberately mirrors exactly what a file contains and nothing more.

# Definition

Fields:

- **`cid`** — concept id: the file path relative to the bundle root, `.md` stripped (e.g. `tables/users`). Empty string for the bundle-root reserved files.
- **`path`** / **`root`** — absolute paths to the file and the bundle root.
- **`frontmatter`** — all parsed frontmatter keys (unknown/extension keys preserved); `{}` when absent or unparseable.
- **`body`** — raw Markdown body, no frontmatter.
- **`reserved`** — `'index'` / `'log'` for reserved filenames, else `None`.
- **`frontmatter_error`** — set when a block was present but invalid; `None` when clean or absent. The validator turns this into an error.
- **`frontmatter_present`** — `True` if the file opened with `---` (even empty), letting the validator distinguish "missing" from "present-but-empty".

# Examples

`Concept` is built only by [parse module](/core/parse.md) and consumed by validate/links/search/context/index. Its twin `serialize_concept` writes it back, preserving frontmatter key order for clean round-trips. See [Permissive parsing](/architecture/permissive-parsing.md).