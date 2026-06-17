---
type: Architecture
title: okf-kit architecture
description: One pure Python core, two thin presentation layers (CLI + MCP), no duplicated
  logic — plus an on-demand web UI.
---
# Overview

`okf-kit` is agent-native tooling for OKF, not a hosted web app. The whole project is **one Python package with one pure core and two thin presentation layers** over it. Every capability — parsing, validation, search, progressive-context reading, index generation, scaffolding — lives in `okf_kit.core`. The `okf` CLI and the `okf-mcp` server are each just a presentation shell that calls the same core functions; logic is never duplicated between them.

# Definition

```
okf_kit.core  (model · parse · validate · links · search · context · index · templates)
      │
      ├── okf_kit.cli   → `okf` CLI      (argparse: init/new/validate/search/read/index/serve)
      └── okf_kit.mcp   → `okf-mcp`      (FastMCP/stdio: search/read_concept/validate + create_concept/init_bundle)
```

The core is **pure**: deterministic, no network, no randomness, 100% unit-tested. That purity is what makes the two presentation layers trivially thin and lets a third consumer (the web UI) reuse the exact same calls.

A read-only web UI (`okf serve`) is a third, on-demand consumer: a stdlib `http.server` over the same core, launched by a harness when a human wants to browse — it is NOT started by `okf-mcp`. See [okf serve](/interfaces/okf-serve.md).

# Examples

Two design commitments are load-bearing across the whole codebase: [Progressive context](/architecture/progressive-context.md) (agents load the minimum and expand under a token budget) and [Path containment](/architecture/path-containment.md) (every id and link target is confined to the bundle root). The permissive-validation stance — parser never raises, validator is the only judge — is documented in [Permissive parsing](/architecture/permissive-parsing.md).