# Authoring an OKF bundle

Build a knowledge base with OKF. Building is done via the `okf` CLI and the
`okf-author` skill — the agent writes `.md` files directly (OKF is just
Markdown); the `okf-mcp` server is read+validate.

## The loop

1. **Init** — `okf init mykb` creates `mykb/index.md` declaring `okf_version`.
2. **Create** — `okf new mykb Table tables/users --title "Users" --desc "..."`.
   Built-in types: `Table`, `Metric`, `Runbook`, `Playbook`, `API` (or any custom
   value → generic body scaffold).
3. **Author** — fill the body; use `# Schema`, `# Examples`, `# Citations`
   conventions where they fit.
4. **Link** — add **relative** links (`[churn](../metrics/churn.md)`); find
   targets with `okf search mykb "<term>"`.
5. **Validate** — `okf validate mykb`. Fix errors (missing frontmatter, empty
   `type`); warnings/info are non-blocking.
6. **Index** — `okf index regen mykb` writes per-directory `index.md` (concepts
   grouped by type + subdirectory links). **Caution:** regen overwrites each
   `index.md` body — back up a hand-authored root `index.md` first, or avoid
   running it on a root you've curated (see `docs/backlog.md`).

## Concept frontmatter

| Field | Status | Notes |
|---|---|---|
| `type` | **required**, non-empty | Any string; producer-defined. |
| `title` | recommended | Display name; derived from id if omitted. |
| `description` | recommended | One-sentence summary; used in `index.md`, search snippets. |
| `resource` | recommended | Canonical URI of the asset; absent for abstract concepts. |
| `tags` | recommended | List of strings. |
| `timestamp` | recommended | ISO 8601 datetime. |
| *(any other)* | allowed | Extension keys are preserved (round-tripped), reported as `info` by validate. |

## Rules

- Reserved filenames `index.md` and `log.md` are **not** concepts — never give
  them a `type`.
- Concept ids use path segments matching `[A-Za-z0-9_][A-Za-z0-9_.-]*`.
- Unknown types and extension keys are tolerated (OKF is a permissive consumer).
