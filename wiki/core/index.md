
# Module
* [core/context — progressive loader](context.md) - read_concept and the depth-N BFS neighborhood loader — the single context primitive, deterministic, cycle-safe, token-budgeted.
* [core/index — index.md regeneration](index-regen.md) - regenerate_indexes writes a type-grouped, per-directory index.md for every directory containing a concept; root index preserves okf_version.
* [core/links — graph + containment](links.md) - Link extraction/resolution, adjacency & backlinks, and the shared path-containment guard (segment validation + resolved-path confinement).
* [core/model — Concept dataclass](model.md) - The Concept dataclass — the in-memory representation of one OKF file (cid, path, frontmatter, body, reserved, diagnostics).
* [core/parse — frontmatter splitting](parse.md) - split_frontmatter, parse_concept, serialize_concept — permissive frontmatter handling that never raises and round-trips cleanly.
* [core/search — full-text ranking](search.md) - A dependency-free inverted index with weighted ranking (title > tag > type > description > body) and type/tag filters; deterministic order.
* [core/templates — scaffolding](templates.md) - init_bundle and create_concept — bundle scaffolding and per-type concept templates, with cid validation and atomic exclusive writes.
* [core/validate — conformance](validate.md) - validate_bundle walks a bundle, classifies every .md into errors/warnings/info, and returns a Report — the only judge of conformance.
