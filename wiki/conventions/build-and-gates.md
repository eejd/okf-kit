---
type: Guide
title: Build & gates
description: How to build and verify okf-kit — uv, pytest, ruff, mypy --strict; core
  is pure and test-first; tool docs stay in sync.
---
# Overview

`okf-kit` is built with Python 3.12+ and `uv`. The project is one package, two console entry points (`okf`, `okf-mcp`). The `core/` package is pure — deterministic, no network, no randomness — and is written test-first at 100% unit coverage. The CLI and MCP are thin shells that never duplicate core logic.

# Definition

Build & verify:

- **Install** — `uv sync` (or `python -m venv .venv && pip install -e ".[dev]"`).
- **Tests** — `uv run pytest`.
- **Gates** — `uv run ruff check . && uv run mypy okf_kit` (mypy is `--strict`).
- **Scaffold** — `uv run okf init mykb`; `uv run okf new mykb Table tables/users`; `uv run okf validate mykb`; `uv run okf index regen mykb`.

New core code ⇒ tests first / alongside. Match existing style. `cli` and `mcp` are presentation layers — if you find yourself adding logic to both, it belongs in `core/`.

# Examples

The other load-bearing conventions are [Tool doc sync](/conventions/tool-doc-sync.md) (descriptions kept identical across three places with an asserting test) and the two design commitments in [architecture](/architecture/overview.md). Conformance is permissive — never raise on missing optional fields or broken links — see [Conformance](/format/conformance.md).