
# Architecture
* [okf-kit architecture](overview.md) - One pure Python core, two thin presentation layers (CLI + MCP), no duplicated logic — plus an on-demand web UI.
* [Path containment (security)](path-containment.md) - How every concept id and link target is confined to the bundle root — segment validation plus resolved-path containment, including symlink escapes, on both read and write paths.
* [Permissive parsing](permissive-parsing.md) - The parser never raises on malformed input — it degrades gracefully and records a diagnostic; the validator is the single judge of conformance.
* [Progressive context](progressive-context.md) - The load-bearing commitment — agents load the minimum and expand on demand under a token budget: search → read depth=0 → read depth=N.
