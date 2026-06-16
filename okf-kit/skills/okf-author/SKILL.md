---
name: okf-author
description: Use when authoring or extending an OKF (Open Knowledge Format) knowledge bundle — creating concepts, writing YAML frontmatter + Markdown body, cross-linking concepts, validating OKF v0.1 conformance (SPEC §9), and regenerating index.md. Runs the scaffold → author → link → validate → index loop via the `okf` CLI.
---

# okf-author

Author and extend an **OKF (Open Knowledge Format)** knowledge bundle. A bundle
is a directory of Markdown files; each file is one *concept* (YAML frontmatter +
body), the file path is its id, and relative Markdown links form a knowledge
graph. Every concept needs a non-empty `type`; recommended fields are `title`,
`description`, `resource`, `tags`, `timestamp`.

## The loop: scaffold → author → link → validate → index

Use the `okf` CLI (installed with the `okf-kit` package).

1. **Scope** — decide the concept's `type` and id (path without `.md`, e.g.
   `tables/users`). Built-in types: `Table`, `Metric`, `Runbook`, `Playbook`,
   `API` — or invent one (OKF types are producer-defined).
2. **Scaffold** — `okf new <bundle> <type> <id> --title "..." --desc "..."`
   writes a correctly-frontmatter'd stub + body scaffold. New bundle?
   `okf init <dir>` first.
3. **Author** — fill the body. Use the conventional headings where they fit:
   `# Schema` (structured columns/fields), `# Examples`, `# Citations`.
4. **Link** — add **relative** Markdown links to related concepts, e.g.
   `[churn](../metrics/churn.md)`. Use `okf search <bundle> "<term>"` to find
   link targets. Prefer relative links — absolute (`/...`) and external (`://`)
   links are not graph edges in v0.1.
5. **Validate** — `okf validate <bundle>` (add `--json` for CI). Fix every
   **error** (missing frontmatter, empty `type`, malformed reserved files).
   Warnings (missing `title`/`description`, broken links) and info (unknown
   types, extension keys) are non-blocking.
6. **Index** — `okf index regen <bundle>` regenerates per-directory `index.md`
   (concepts grouped by type + subdirectory links).

## Read back (and gather context)

- `okf read <bundle> <id>` — one concept.
- `okf read <bundle> <id> --depth 1` — the concept **plus** its link
  neighborhood (progressive context), token-budgeted. Start at depth 0; raise
  depth only when you need surrounding context.

## Rules

- `type` is the only required frontmatter field — never leave it empty.
- Preserve extension frontmatter keys you didn't author (OKF is permissive;
  consumers must round-trip unknown keys).
- Reserved filenames `index.md` and `log.md` are **not** concepts — never give
  them a `type`.
- Concept ids use path segments matching `[A-Za-z0-9_][A-Za-z0-9_.-]*` (no
  spaces, no `..`).
