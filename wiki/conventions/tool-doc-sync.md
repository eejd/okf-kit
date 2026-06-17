---
type: Guide
title: Tool doc sync
description: Every tool is documented in three synced places — MCP description, CLI
  --help, and the reference/tools wiki concept — and a test asserts they match.
---
# Overview

A load-bearing convention (design §11): every tool's human/agent-facing description is documented in **three places** and kept identical — the MCP tool `description`, the CLI `--help`, and the canonical [Tool reference](/reference/tools.md) wiki concept. That wiki concept is the source of truth; the others copy it verbatim. A test (`okf-kit/tests/test_docs.py`) asserts they stay in sync, so a description drift is caught at gate time.

# Definition

Why three places: the MCP `description` is the **agent trigger surface** (what makes an LLM call the right tool); the CLI `--help` is the **human surface**; the `reference/tools` wiki concept is the **reviewable, diffable reference**. One sentence in three windows means an agent, a human at a shell, and a PR reviewer all see the same contract.

The MCP tool descriptions live as `_SEARCH_DESC`, `_READ_DESC`, `_VALIDATE_DESC`, `_CREATE_DESC`, `_INIT_DESC` in [okf-mcp](/interfaces/okf-mcp.md); the CLI help strings live next to each subparser in [okf CLI](/interfaces/okf-cli.md).

# Steps

When changing a tool's behavior:

1. Edit the `reference/tools` wiki concept first (source of truth) — update its `<!-- desc:start -->` … `<!-- desc:end -->` block.
2. Copy the new description verbatim into the MCP `_…_DESC` constant and the CLI `--help`.
3. Run `uv run pytest okf-kit/tests/test_docs.py` — it fails if any of the three drifted.

See [Build & gates](/conventions/build-and-gates.md); the tools themselves are documented in [Tool reference](/reference/tools.md).