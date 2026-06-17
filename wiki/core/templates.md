---
type: Module
title: core/templates — scaffolding
description: init_bundle and create_concept — bundle scaffolding and per-type concept
  templates, with cid validation and atomic exclusive writes.
---
# Overview

`okf_kit/core/templates.py` is the producer side (REQ-ED-05, REQ-PROD-08): `init_bundle` scaffolds a new bundle root; `create_concept` writes a concept from a built-in type template. Concept ids are validated against the SPEC §2.2 segment regex, which also guarantees the written path stays inside the bundle root.

# Definition

Built-in template types: `Table`, `Metric`, `Runbook`, `Playbook`, `API` (plus a `_generic` fallback). Each ships a body skeleton with a depth heading (`# Schema`, `# Definition`, `# Steps`, `# Endpoints`, `# Overview`).

- **`init_bundle(root, okf_version='0.1', name=None)`** — `mkdir -p`, then write a root `index.md` whose only frontmatter is `okf_version` and whose body is `# <name or dir name>`.
- **`create_concept(root, cid, type, *, title, description, tags, body, extra)`** — validate `cid` segments; check the **parent** of the candidate path is contained (write-path mirror of `resolve_cid_path`); assemble frontmatter (`type` plus optional `title`/`description`/`tags`/`extra`); `mkdir -p` the parent; open with mode `"x"` (`O_CREAT|O_EXCL`) so an existing file is never clobbered — atomic exclusive create with no TOCTOU window.

A missing `body` falls back to the type template; an explicit body (as the MCP tool always sends) replaces it.

# API

The CLI `init` / `new` commands and the MCP `init_bundle` / `create_concept` tools both delegate here. The MCP layer adds the **richness floor** on top — see [okf-mcp](/interfaces/okf-mcp.md). Containment details in [Path containment](/architecture/path-containment.md).