"""The ``okf-mcp`` server (FastMCP, stdio).

Exposes an OKF bundle to MCP clients (Claude Code, Antigravity, any MCP client)
as five tools — ``search``, ``read_concept``, ``validate``, ``create_concept``,
``init_bundle`` — plus an
``okf://<bundle>/concepts/<cid>.md`` resource per concept. Tools are thin
wrappers over :mod:`okf_kit.core`; the bundle is registered at startup by
directory name.

Tool descriptions are the agent trigger surface (design §11); the
``wiki/reference/tools.md`` concept is the source of truth and a test asserts
they stay in sync.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from okf_kit.core import context as context_mod
from okf_kit.core.links import iter_concept_files
from okf_kit.core.parse import parse_concept
from okf_kit.core.search import Hit, build_index, search
from okf_kit.core.templates import create_concept, init_bundle
from okf_kit.core.validate import validate_bundle

_SEARCH_DESC = (
    "Discover OKF concepts without loading full bodies. Searches title, description, body, "
    "tags, and type, then returns ranked hits with cid/title/type/snippet/score. Use this "
    "before read_concept when you do not already know the concept id, and narrow with "
    "type[] or tag[] when the bundle is large. Empty query lists concepts after filters. "
    "Example: search(bundle='analytics', query='customer churn', type=['Metric','Table'])."
)

_READ_DESC = (
    "Read a concept by id, or progressively load its linked neighborhood. depth=0 returns "
    "only that concept's raw frontmatter plus Markdown body. depth=1..N returns the seed in "
    "full plus Markdown-linked neighbors in deterministic BFS order within token_budget; a "
    "trailing marker names omitted neighbors. Start at depth=0, then increase depth only when "
    "the answer needs surrounding context. Example: read_concept(bundle='analytics', "
    "concept_id='metrics/churn', depth=1)."
)

_VALIDATE_DESC = (
    "Validate an OKF bundle against v0.1 conformance (SPEC §9). Returns "
    "{conformant, errors, warnings, info}. Errors such as missing frontmatter, invalid "
    "frontmatter, or empty type block conformance. Warnings such as missing title/description, "
    "invalid cids, and broken links are non-blocking. Info includes extension keys, nested "
    "sub-bundle markers, okf_version state, and empty bundles. Use after authoring and before "
    "publishing or CI. Example: validate(bundle='analytics')."
)

_CREATE_DESC = (
    "Create one substantive OKF concept. Use after searching/reading nearby concepts so the "
    "new page is specific, linked, and non-duplicative. The body must be >=120 words and "
    "include at least one depth heading: # Overview, # Definition, # Schema, # Endpoints, "
    "# API, # Steps, # Examples, or # Citations. Write concrete Markdown with relevant "
    "headings, examples, caveats, and bundle-relative links such as [Users](/tables/users.md); "
    "do not create placeholders or generic filler. Returns the created cid and path; rejects "
    "thin bodies, invalid ids, path escapes, and existing files."
)

_INIT_DESC = (
    "Initialize a registered OKF bundle root by writing root index.md with okf_version. "
    "Creates the directory if needed and rewrites index.md if it already exists, so use it "
    "before authoring a new bundle or when intentionally resetting the root index metadata. "
    "Example: init_bundle(bundle='wiki')."
)

BundleName = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Registered bundle name. When okf-mcp is launched from the CLI, this is the "
            "bundle directory name."
        ),
    ),
]
SearchQuery = Annotated[
    str,
    Field(
        description=(
            "Search terms. Use an empty string only when you intentionally want to list all "
            "concepts after applying filters."
        )
    ),
]
TypeFilter = Annotated[
    list[str] | None,
    Field(description="Optional exact type filters, for example ['Table', 'Metric']."),
]
TagFilter = Annotated[
    list[str] | None,
    Field(description="Optional exact tag filters. A concept matches if it has any listed tag."),
]
SearchLimit = Annotated[
    int,
    Field(ge=1, le=100, description="Maximum number of hits to return."),
]
ConceptId = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$",
        description=(
            "Bundle-relative concept id without .md, such as 'tables/users'. Segments must "
            "match [A-Za-z0-9_][A-Za-z0-9_.-]*."
        ),
    ),
]
Depth = Annotated[
    int,
    Field(
        ge=0,
        le=5,
        description="Neighborhood depth. Use 0 for one concept; increase only when links matter.",
    ),
]
TokenBudget = Annotated[
    int,
    Field(
        ge=500,
        le=50000,
        description=(
            "Approximate token budget for depth>0 context. The seed concept is always included "
            "in full; neighbors may be omitted."
        ),
    ),
]
ConceptType = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Concept type stored in frontmatter. Built-ins include Table, Metric, Runbook, "
            "Playbook, and API; custom types are allowed."
        ),
    ),
]
ConceptTitle = Annotated[
    str,
    Field(min_length=1, description="Human-readable title for the concept frontmatter."),
]
ConceptDescription = Annotated[
    str,
    Field(
        min_length=1,
        description="One-sentence, specific summary used in search results and indexes.",
    ),
]
ConceptBody = Annotated[
    str,
    Field(
        min_length=1,
        description=(
            "Substantive Markdown body, not a stub. Must be >=120 words and include at least "
            "one accepted depth heading (# Overview, # Definition, # Schema, # Endpoints, "
            "# API, # Steps, # Examples, or # Citations). Prefer concrete facts, examples, "
            "relationships, caveats, and bundle-relative Markdown links to related concepts."
        ),
    ),
]
Tags = Annotated[
    list[str] | None,
    Field(description="Optional short tags for filtering and discovery."),
]
ConceptResource = Annotated[
    str | None,
    Field(
        description=(
            "Optional canonical URI of the underlying asset (SPEC §2.3). Omit for "
            "abstract concepts; e.g. 'bigquery://proj.datasets.ds.tables.users'."
        )
    ),
]
Timestamp = Annotated[
    str | None,
    Field(description="Optional ISO-8601 'last meaningful change' timestamp (SPEC §2.3)."),
]
ExtraFrontmatter = Annotated[
    dict[str, Any] | None,
    Field(
        description=(
            "Optional extra/extension frontmatter keys to write and preserve "
            "(SPEC §2.3 extension policy). Explicit resource/timestamp args override "
            "a same-named key here."
        )
    ),
]
OkfVersion = Annotated[
    str,
    Field(description="OKF version to write in root index.md frontmatter.", min_length=1),
]


class BundleRegistry:
    """Maps a registered bundle name to its resolved root path."""

    def __init__(self, bundles: dict[str, Any]) -> None:
        self._bundles: dict[str, Path] = {
            name: Path(path).resolve() for name, path in bundles.items()
        }

    def get(self, name: str) -> Path:
        if name not in self._bundles:
            registered = ", ".join(self._bundles) or "none"
            raise KeyError(f"unknown bundle {name!r} (registered: {registered})")
        return self._bundles[name]

    def names(self) -> list[str]:
        return sorted(self._bundles)


def tool_search(
    reg: BundleRegistry,
    bundle: BundleName,
    query: SearchQuery,
    type: TypeFilter = None,
    tag: TagFilter = None,
    limit: SearchLimit = 20,
) -> list[dict[str, Any]]:
    index = build_index(reg.get(bundle))
    return [_hit_dict(h) for h in search(index, query, type=type, tag=tag, limit=limit)]


def tool_read_concept(
    reg: BundleRegistry,
    bundle: BundleName,
    concept_id: ConceptId,
    depth: Depth = 0,
    token_budget: TokenBudget = 8000,
) -> str:
    return context_mod.read_concept(
        reg.get(bundle), concept_id, depth=depth, token_budget=token_budget
    )


def tool_validate(reg: BundleRegistry, bundle: BundleName) -> dict[str, Any]:
    return validate_bundle(reg.get(bundle)).to_dict()


# Richness floor — the mechanism that makes "created via MCP => good info".
_RICH_MIN_WORDS = 120
_RICHNESS_SECTIONS = frozenset(
    {"examples", "schema", "api", "citations", "steps", "definition", "endpoints", "overview"}
)


def _check_richness(body: str) -> None:
    """Reject thin concept bodies (too few words, or no depth section)."""
    words = len(body.split())
    sections = {
        line[2:].strip().lower() for line in body.splitlines() if line.startswith("# ")
    }
    found = sections & _RICHNESS_SECTIONS
    problems: list[str] = []
    if words < _RICH_MIN_WORDS:
        problems.append(f"{words} words (need >= {_RICH_MIN_WORDS})")
    if not found:
        problems.append(
            "no depth section (add one of: " + ", ".join(sorted(_RICHNESS_SECTIONS)) + ")"
        )
    if problems:
        raise ValueError("concept body is too thin: " + "; ".join(problems))


def tool_create_concept(
    reg: BundleRegistry,
    bundle: BundleName,
    cid: ConceptId,
    type: ConceptType,
    title: ConceptTitle,
    description: ConceptDescription,
    body: ConceptBody,
    tags: Tags = None,
    resource: ConceptResource = None,
    timestamp: Timestamp = None,
    extra: ExtraFrontmatter = None,
) -> dict[str, Any]:
    """Create a concept via MCP, enforcing the richness floor.

    Forwards all recommended frontmatter (title/description/tags/resource/timestamp)
    plus arbitrary extension keys (``extra``) to ``core.templates.create_concept``.
    An explicit ``resource``/``timestamp`` arg overrides a same-named ``extra`` key.
    """
    _check_richness(body)
    extra_fm: dict[str, Any] = dict(extra) if extra else {}
    if resource is not None:
        extra_fm["resource"] = resource
    if timestamp is not None:
        extra_fm["timestamp"] = timestamp
    path = create_concept(
        reg.get(bundle),
        cid,
        type,
        title=title,
        description=description,
        tags=tags,
        body=body,
        extra=extra_fm or None,
    )
    return {"created": True, "cid": cid, "path": str(path)}


def tool_init_bundle(
    reg: BundleRegistry, bundle: BundleName, okf_version: OkfVersion = "0.1"
) -> dict[str, Any]:
    """Initialize a bundle root via MCP (idempotent)."""
    path = init_bundle(reg.get(bundle), okf_version=okf_version)
    return {"initialized": True, "path": str(path)}


def make_server(bundles: dict[str, Any]) -> FastMCP:
    """Build a FastMCP server with tools + per-concept ``okf://`` resources."""
    reg = BundleRegistry(bundles)
    server = FastMCP("okf")

    @server.tool(
        name="search",
        title="Search concepts",
        description=_SEARCH_DESC,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def _search(
        bundle: BundleName,
        query: SearchQuery,
        type: TypeFilter = None,
        tag: TagFilter = None,
        limit: SearchLimit = 20,
    ) -> list[dict[str, Any]]:
        return tool_search(reg, bundle, query, type, tag, limit)

    @server.tool(
        name="read_concept",
        title="Read concept",
        description=_READ_DESC,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def _read_concept(
        bundle: BundleName,
        concept_id: ConceptId,
        depth: Depth = 0,
        token_budget: TokenBudget = 8000,
    ) -> str:
        return tool_read_concept(reg, bundle, concept_id, depth, token_budget)

    @server.tool(
        name="validate",
        title="Validate bundle",
        description=_VALIDATE_DESC,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def _validate(bundle: BundleName) -> dict[str, Any]:
        return tool_validate(reg, bundle)

    @server.tool(
        name="create_concept",
        title="Create concept",
        description=_CREATE_DESC,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    def _create_concept(
        bundle: BundleName,
        cid: ConceptId,
        type: ConceptType,
        title: ConceptTitle,
        description: ConceptDescription,
        body: ConceptBody,
        tags: Tags = None,
        resource: ConceptResource = None,
        timestamp: Timestamp = None,
        extra: ExtraFrontmatter = None,
    ) -> dict[str, Any]:
        return tool_create_concept(
            reg, bundle, cid, type, title, description, body, tags, resource, timestamp, extra
        )

    @server.tool(
        name="init_bundle",
        title="Initialize bundle",
        description=_INIT_DESC,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def _init_bundle(bundle: BundleName, okf_version: OkfVersion = "0.1") -> dict[str, Any]:
        return tool_init_bundle(reg, bundle, okf_version)

    _register_resources(server, reg)
    return server


def _register_resources(server: FastMCP, reg: BundleRegistry) -> None:
    def make_reader(path: Path) -> Callable[[], str]:
        # Static resource readers must take no params (FastMCP matches URI params
        # to function params); close over the path instead.
        def _reader() -> str:
            return path.read_text(encoding="utf-8")

        return _reader

    for name in reg.names():
        root = reg.get(name)
        for md in iter_concept_files(root):
            concept = parse_concept(md, root)
            if concept.reserved is not None:
                continue
            cid = concept.cid
            uri = f"okf://{name}/concepts/{cid}.md"
            title_value = concept.frontmatter.get("title")
            desc_value = concept.frontmatter.get("description")
            title = title_value if isinstance(title_value, str) else cid
            description = desc_value if isinstance(desc_value, str) else ""
            server.resource(uri, name=title, description=description)(make_reader(concept.path))


def _hit_dict(hit: Hit) -> dict[str, Any]:
    return {
        "cid": hit.cid,
        "title": hit.title,
        "type": hit.type,
        "snippet": hit.snippet,
        "score": hit.score,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="okf-mcp",
        description="OKF MCP server (stdio). Registers each bundle by its directory name.",
    )
    parser.add_argument(
        "bundles", nargs="+", help="Bundle directories to serve (registered by directory name)."
    )
    args = parser.parse_args(argv)
    bundles = {Path(b).name: Path(b) for b in args.bundles}
    make_server(bundles).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
