---
type: Guide
title: Authoring a bundle
description: How to build an OKF bundle — the init → create → author → link → validate
  → index loop, frontmatter fields, and the reserved-filename rules.
---
# Overview

Build a knowledge base with OKF. Building is done with the `okf` CLI and the `okf-author` skill — the agent writes `.md` files directly (OKF is just Markdown); [okf-mcp](/interfaces/okf-mcp.md) is read + validate, and its `create_concept` tool additionally enforces a richness floor so MCP-authored pages are substantive. Use `okf-search` for read-only progressive-context investigation, `okf-author` for both create and update authoring loops, and `okf-code` when a codebase should be indexed into OKF `CodeModule` concepts. Install the standard skills with `okf agent install claude-code|codex --scope project`; this installer is skill-only and does not install subagents or hooks. For build/gate commands see [Build & gates](/conventions/build-and-gates.md); for the CLI subcommands see [okf CLI](/interfaces/okf-cli.md).

# Steps

The author → link → validate → index loop:

1. **Init** — `okf init mykb` creates `mykb/index.md` declaring `okf_version`.
2. **Create** — `okf new mykb Table tables/users --title "Users" --desc "…"`. Built-in types: `Table`, `Metric`, `Runbook`, `Playbook`, `API` (or any custom value).
3. **Author or update** — fill or edit the body; use the `# Schema`, `# Examples`, `# Citations` conventions where they fit. Preserve extension frontmatter keys unless the task explicitly changes them.
4. **Link** — add links between concepts; the spec recommends absolute (leading-slash, bundle-relative) form, relative also works. Find targets with `okf search mykb "<term>"`. See [Links](/format/links.md).
5. **Validate** — `okf validate mykb`. Fix errors (missing frontmatter, empty `type`); warnings/info are non-blocking. See [Conformance](/format/conformance.md).
6. **Index** — `okf index regen mykb` writes per-directory `index.md`. **Caution:** regen overwrites each `index.md` body — back up a hand-authored root first (see [Backlog](/project/backlog.md)).

For code repositories, install `okf-kit[treesitter]` and run
`okf code index <repo> <bundle>` to generate managed `CodeModule` concepts under
`code/`. The default scans Python, Java, Scala, Rust, Go, Kotlin, Perl, C#,
PHP, TypeScript, JavaScript, and HTML; repeat `--language` to narrow the run.
Then search and read those concepts the same way: `okf search <bundle>
"symbol"` followed by `okf read <bundle> <id> --depth 1`. Generated impact
notes are syntax-derived candidates, not complete semantic proof.

# Definition

Concept frontmatter: `type` is the only required field (non-empty, producer-defined). Recommended: `title`, `description`, `resource`, `tags`, `timestamp`. Any other key is an extension key — preserved on round-trip, reported as `info` by validate. Reserved filenames `index.md` and `log.md` are **not** concepts — never give them a `type`. Concept id segments match `[A-Za-z0-9_][A-Za-z0-9_.-]*`.
