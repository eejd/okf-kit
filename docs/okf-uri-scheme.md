# The `okf://` resource scheme

The `okf-mcp` server exposes each concept as an addressable MCP **resource**:

```
okf://<bundle>/concepts/<concept-id>.md
```

- `<bundle>` — the registered bundle name (the directory name passed to
  `okf-mcp <dir>`).
- `<concept-id>` — the concept id, i.e. the file path relative to the bundle
  root without `.md` (e.g. `tables/users`). May span directories.

## Examples

- `okf://analytics/concepts/tables/users.md`
- `okf://analytics/concepts/metrics/churn.md`

Reading a resource returns the concept's raw Markdown (frontmatter + body). The
resource's MCP `name`/`description` carry the concept's `title`/`description`.

## Notes (v0.1)

- Resources are enumerated at server startup — a snapshot. Restart the server
  after authoring new concepts so they appear.
- The same content is available via the `read_concept` tool (which also supports
  `depth` neighborhood expansion). Prefer `read_concept` when you need context;
  use the resource URI for stable addressing.
- Bundle identifiers are **paths**, not flat names — this keeps the door open to
  future multi-level bundles (`<domain>/<subdomain>`) without a schema change.
