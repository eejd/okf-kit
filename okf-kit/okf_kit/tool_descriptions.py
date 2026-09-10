"""Canonical CLI/MCP tool descriptions shared by both presentation layers."""

SEARCH_DESC = (
    "Discover OKF concepts without loading full bodies. Searches title, description, body, "
    "tags, and type, then returns ranked hits with cid/title/type/snippet/score. Use this "
    "before read_concept when you do not already know the concept id, and narrow with "
    "type[], tag[], or exact metadata facets when the bundle is large. Returns a page with "
    "schema_version, results, total, and an opaque next_cursor bound to the query, filters, "
    "and bundle revision. Set response_version='legacy' while migrating pre-0.3 list clients. "
    "Empty query lists concepts after filters. "
    "Example: search(bundle='analytics', query='customer churn', type=['Metric','Table'])."
)

READ_DESC = (
    "Read a concept by id, or progressively load its linked neighborhood. depth=0 returns "
    "only that concept's raw frontmatter plus Markdown body. depth=1..N returns the seed in "
    "full plus neighbors in the selected outgoing, incoming, or both direction in deterministic "
    "BFS order within token_budget; a trailing marker names omitted neighbors. Start at depth=0, "
    "then increase depth only when the answer needs surrounding context. Example: "
    "read_concept(bundle='analytics', concept_id='metrics/churn', depth=1)."
)

VALIDATE_DESC = (
    "Validate an OKF bundle against v0.2 conformance (SPEC §11). Returns "
    "{conformant, publishable, errors, publication_errors, warnings, info}. Generic OKF "
    "conformance stays permissive; an optional server publication profile adds publishability "
    "checks without changing conformance. Errors such as missing frontmatter, invalid "
    "frontmatter, or empty type block conformance. Warnings such as missing title/description, "
    "invalid cids, and broken links are non-blocking. Info includes extension keys, nested "
    "sub-bundle markers, okf_version state, and empty bundles. Use after authoring and before "
    "publishing or CI. Example: validate(bundle='analytics')."
)

GRAPH_DESC = (
    "Traverse graph edges without loading concept bodies. Returns typed incoming, outgoing, "
    "or bidirectional edges for one concept, including cross-bundle okf:// relations when the "
    "target bundle, including a multi-level bundle id, is registered. Filter by relation when "
    "only governs, implements, depends-on, evidence-for, supersedes, related, or ordinary "
    "Markdown links matter."
)

CREATE_DESC = (
    "Create one substantive draft OKF concept on the configured preview branch. The server "
    "verifies its expected branch before writing and again before commit/push, controls status "
    "and generated provenance, and rejects caller-supplied verified/trust fields. Use after "
    "searching/reading nearby concepts so the new page is specific, linked, and non-duplicative. "
    "The body must be >=120 words and include at least one depth heading: # Overview, "
    "# Definition, # Schema, # Endpoints, # API, # Steps, # Examples, or # Citations. Write "
    "concrete Markdown with relevant headings, examples, caveats, and bundle-relative links such "
    "as [Users](/tables/users.md); do not create placeholders or generic filler. Returns the "
    "created cid and path; rejects thin bodies, invalid ids, path escapes, and existing files."
)

INIT_DESC = (
    "Initialize a registered OKF bundle root in the preview lane by writing root index.md with "
    "okf_version after verifying the expected write branch. Creates the directory if needed and "
    "rewrites index.md if it already exists, so use it before authoring a new bundle or when "
    "intentionally resetting the root index metadata. Example: init_bundle(bundle='wiki')."
)

LIST_BUNDLES_DESC = (
    "List every bundle name registered on this server, alphabetically sorted (not registration "
    "order), the only valid values for the 'bundle' argument every other tool requires. Call "
    "this first if you don't already know the registered name — it is not always the same as "
    "the corpus's conceptual name (e.g. a server may register a bundle as 'bundle' if that is "
    "its mount directory's basename). Example: list_bundles()."
)

SYNC_STATUS_DESC = (
    "Report a bundle's authority lane and git reconciliation state: lane, write_mode, expected "
    "write branch, served SHA, configured upstream ref and SHA, branch, dirty state, and whether "
    "the checkout is in-sync, ahead, behind, or diverged. Returns tracked=false outside a git "
    "repository."
)
