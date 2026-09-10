"""The ``okf-mcp`` server (FastMCP, transport-agnostic).

Exposes OKF bundles to MCP clients with stable read tools, preview-only draft
write tools, and one ``okf://<bundle>/concepts/<cid>.md`` resource per concept.
Tools are thin wrappers over :mod:`okf_kit.core`.

Bundle registration: each CLI positional argument is either a bare path
(registered under its directory basename, the original behavior — e.g. a
container mounting a bundle at ``/bundle`` registers it as ``bundle``) or an
explicit ``NAME=PATH`` form to give a bundle a name independent of its mount
point or directory name. Registering two bundles under the same name is a
startup error, not a silent overwrite.

Transports (selectable at runtime via ``--transport``):
  stdio           — default; classic pipe/subprocess mode.
  streamable-http — HTTP+SSE, binds loopback (127.0.0.1) by default.
  sse             — legacy SSE-only HTTP mode.

When running HTTP transport, host and port are set on ``make_server()``
(passed to the :class:`FastMCP` constructor) so DNS-rebinding protection is
activated automatically for loopback binds.

Tool descriptions are the agent trigger surface (design §11); the
``wiki/reference/tools.md`` concept is the source of truth and a test asserts
they stay in sync.

Every tool call emits one structured JSON line to **stderr** (never stdout —
under stdio transport, stdout is the MCP JSON-RPC wire itself, and writing
logs there would corrupt the protocol stream). This is Phase 1 of an
instrumentation-before-splitting plan: rather than guessing whether/how to
segregate a bundle, collect real usage signals first (zero-result rate,
concept-read locality, bundle growth) and let that data decide. See
:func:`_log_tool_call`.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from okf_kit import tool_descriptions
from okf_kit.core import context as context_mod
from okf_kit.core.gitio import GitWriter
from okf_kit.core.links import GraphEdge, concept_graph_edges, iter_concept_files, resolve_cid_path
from okf_kit.core.parse import parse_concept
from okf_kit.core.search import Hit, build_index, search_page
from okf_kit.core.templates import create_concept, init_bundle
from okf_kit.core.validate import validate_bundle

_CREATE_DESC = tool_descriptions.CREATE_DESC
_GRAPH_DESC = tool_descriptions.GRAPH_DESC
_INIT_DESC = tool_descriptions.INIT_DESC
_LIST_BUNDLES_DESC = tool_descriptions.LIST_BUNDLES_DESC
_READ_DESC = tool_descriptions.READ_DESC
_SEARCH_DESC = tool_descriptions.SEARCH_DESC
_SYNC_STATUS_DESC = tool_descriptions.SYNC_STATUS_DESC
_VALIDATE_DESC = tool_descriptions.VALIDATE_DESC

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
MetadataFilter = Annotated[
    dict[str, Any] | None,
    Field(
        description=(
            "Optional exact frontmatter filters; a scalar matches membership in "
            "list-valued facets."
        )
    ),
]
SearchCursor = Annotated[
    str | None,
    Field(description="Opaque next_cursor returned by an earlier search page."),
]
SearchResponseVersion = Annotated[
    str,
    Field(
        pattern=r"^(v1|legacy)$",
        description=(
            "Response contract: v1 returns a cursor page; legacy returns the pre-0.3 hit list."
        ),
    ),
]
Direction = Annotated[
    str,
    Field(pattern=r"^(outgoing|incoming|both)$", description="Graph traversal direction."),
]
RelationFilter = Annotated[
    list[str] | None,
    Field(description="Optional exact graph relation names to include."),
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


def _log_tool_call(tool: str, started_at: float, ok: bool, **fields: Any) -> None:
    """Emit one structured JSON line to **stderr** for a completed tool call.

    Phase 1 of an instrumentation-before-splitting plan for multi-bundle
    knowledge bases: rather than guessing whether a bundle needs to be split
    into several, collect real usage signals (zero-result queries, which
    concepts get read vs. never touched, per-directory read locality) and
    let that data decide. Deliberately dependency-free (stdlib only) and
    deliberately never raises — a logging failure must never break the tool
    call it describes, matching this codebase's existing "parser never
    raises, validator is the only judge" discipline.

    Deliberately **stderr**, not stdout: under stdio transport, stdout is the
    MCP JSON-RPC wire itself, and writing logs there would corrupt the
    protocol stream.
    """
    try:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "tool": tool,
            "ok": ok,
            "latency_ms": round((time.monotonic() - started_at) * 1000, 2),
        }
        record.update({k: v for k, v in fields.items() if v is not None})
        print(json.dumps(record, default=str), file=sys.stderr, flush=True)
    except Exception:
        pass


class DuplicateBundleNameError(ValueError):
    """Raised when two bundle arguments would register under the same name."""


class BundleRegistry:
    """Maps a registered bundle name to its resolved root path.

    Accepts either a ``dict[name, path]`` directly, or (from the CLI) an
    ordered list of ``(name, path)`` pairs — the list form is what detects a
    duplicate name, since a plain ``dict`` literal would already have
    silently discarded the earlier entry before the registry ever saw it.
    """

    def __init__(self, bundles: dict[str, Any] | list[tuple[str, Any]]) -> None:
        # dict inputs can never trigger the duplicate check below — dict keys
        # are unique by construction, so any duplicate was already silently
        # resolved (last write wins) before this constructor ever sees it.
        # The check only does real work for the list-of-pairs form, which is
        # exactly why the CLI passes bundles as a list rather than a dict.
        items = bundles.items() if isinstance(bundles, dict) else bundles
        resolved: dict[str, Path] = {}
        for name, path in items:
            if name in resolved:
                raise DuplicateBundleNameError(
                    f"bundle name {name!r} is already registered "
                    f"(paths: {resolved[name]} and {Path(path).resolve()}) — "
                    "give each bundle a distinct NAME=PATH"
                )
            resolved[name] = Path(path).resolve()
        self._bundles: dict[str, Path] = resolved

    def get(self, name: str) -> Path:
        if name not in self._bundles:
            registered = ", ".join(self.names()) or "none"
            raise KeyError(f"unknown bundle {name!r} (registered: {registered})")
        return self._bundles[name]

    def names(self) -> list[str]:
        """Registered bundle names, alphabetically sorted (not registration order)."""
        return sorted(self._bundles)


class GitBackend:
    """Per-bundle :class:`GitWriter` cache for the draft write path.

    Discovery (``git rev-parse --show-toplevel`` from the bundle root) runs
    once per bundle, lazily, so a server whose bundles live outside any git
    repository still starts and serves reads normally — the git result on a
    write then reports the discovery failure instead of raising.
    """

    def __init__(self, reg: BundleRegistry) -> None:
        self._reg = reg
        self._writers: dict[str, GitWriter | None] = {}

    def writer_for(self, bundle: str) -> GitWriter | None:
        if bundle not in self._writers:
            self._writers[bundle] = GitWriter.discover(self._reg.get(bundle))
        return self._writers[bundle]

    def require_branch(self, bundle: str, expected_branch: str) -> GitWriter:
        """Verify the configured review branch before any filesystem mutation."""
        writer = self.writer_for(bundle)
        if writer is None:
            raise ValueError("draft writes require a git-tracked bundle")
        writer.require_branch(expected_branch)
        return writer


def tool_search(
    reg: BundleRegistry,
    bundle: BundleName,
    query: SearchQuery,
    type: TypeFilter = None,
    tag: TagFilter = None,
    limit: SearchLimit = 20,
    metadata: MetadataFilter = None,
    cursor: SearchCursor = None,
    response_version: SearchResponseVersion = "v1",
) -> dict[str, Any] | list[dict[str, Any]]:
    started_at = time.monotonic()
    ok = False
    hits: list[Hit] = []
    try:
        if response_version not in {"v1", "legacy"}:
            raise ValueError("response_version must be v1 or legacy")
        if response_version == "legacy" and cursor is not None:
            raise ValueError("legacy search responses do not accept a cursor")
        index = build_index(reg.get(bundle))
        hits, total, next_cursor = search_page(
            index, query, type=type, tag=tag, metadata=metadata, limit=limit, cursor=cursor
        )
        ok = True
        results = [_hit_dict(h) for h in hits]
        if response_version == "legacy":
            return results
        return {
            "schema_version": "1",
            "results": results,
            "total": total,
            "next_cursor": next_cursor,
        }
    finally:
        _log_tool_call(
            "search",
            started_at,
            ok,
            bundle=bundle,
            query=query,
            n_results=len(hits),
            top_score=hits[0].score if hits else None,
        )


def tool_read_concept(
    reg: BundleRegistry,
    bundle: BundleName,
    concept_id: ConceptId,
    depth: Depth = 0,
    token_budget: TokenBudget = 8000,
    direction: Direction = "both",
) -> str:
    started_at = time.monotonic()
    ok = False
    try:
        result = context_mod.read_concept(
            reg.get(bundle), concept_id, depth=depth, token_budget=token_budget, direction=direction
        )
        ok = True
        return result
    finally:
        _log_tool_call(
            "read_concept", started_at, ok, bundle=bundle, concept_id=concept_id, depth=depth
        )


def tool_graph_links(
    reg: BundleRegistry,
    bundle: BundleName,
    concept_id: ConceptId,
    direction: Direction = "both",
    relation: RelationFilter = None,
) -> dict[str, Any]:
    """Return typed graph edges touching one concept across registered bundles."""
    started_at = time.monotonic()
    ok = False
    selected: set[GraphEdge] = set()
    try:
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("direction must be outgoing, incoming, or both")
        if resolve_cid_path(reg.get(bundle), concept_id) is None:
            raise context_mod.ConceptNotFound(concept_id, [])
        allowed = set(relation) if relation else None
        registered = set(reg.names())
        for source_bundle in reg.names():
            root = reg.get(source_bundle)
            for md in iter_concept_files(root):
                concept = parse_concept(md, root)
                if concept.reserved is not None:
                    continue
                for edge in concept_graph_edges(root, concept, source_bundle):
                    if (
                        edge.target_bundle not in registered
                        or resolve_cid_path(reg.get(edge.target_bundle), edge.target_cid) is None
                    ):
                        continue
                    outgoing = edge.source_bundle == bundle and edge.source_cid == concept_id
                    incoming = edge.target_bundle == bundle and edge.target_cid == concept_id
                    touches = (
                        (direction in {"outgoing", "both"} and outgoing)
                        or (direction in {"incoming", "both"} and incoming)
                    )
                    if touches and (allowed is None or edge.relation in allowed):
                        selected.add(edge)
        edges = [edge.to_dict() for edge in sorted(selected)]
        ok = True
        return {
            "bundle": bundle, "concept_id": concept_id,
            "direction": direction, "edges": edges,
        }
    finally:
        _log_tool_call(
            "graph_links", started_at, ok, bundle=bundle, concept_id=concept_id,
            direction=direction, n_edges=len(selected),
        )


def tool_validate(
    reg: BundleRegistry, bundle: BundleName, publication_profile: str | None = None
) -> dict[str, Any]:
    started_at = time.monotonic()
    ok = False
    report: dict[str, Any] = {}
    try:
        report = validate_bundle(reg.get(bundle), profile=publication_profile).to_dict()
        ok = True
        return report
    finally:
        _log_tool_call(
            "validate",
            started_at,
            ok,
            bundle=bundle,
            n_errors=len(report.get("errors", [])) if report else None,
            n_warnings=len(report.get("warnings", [])) if report else None,
            n_info=len(report.get("info", [])) if report else None,
        )


# Richness floor — the mechanism that makes "created via MCP => good info".
_RICH_MIN_WORDS = 120
_RICHNESS_SECTIONS = frozenset(
    {"examples", "schema", "api", "citations", "steps", "definition", "endpoints", "overview"}
)


def _check_richness(body: str) -> None:
    """Reject thin concept bodies (too few words, or no depth section)."""
    words = len(body.split())
    sections = {line[2:].strip().lower() for line in body.splitlines() if line.startswith("# ")}
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


def _git_commit_result(
    git: GitBackend | None,
    bundle: str,
    paths: list[Path],
    message: str,
    *,
    expected_branch: str | None = None,
) -> dict[str, Any] | None:
    """Commit-and-push for a completed write, or ``None`` when git mode is off.

    Never raises: a bundle outside any git repository degrades to a
    structured ``{committed: false, detail: ...}`` result — the file write
    that preceded this call has already succeeded and must never be undone
    or reported as failed because of a git problem.
    """
    if git is None:
        return None
    writer = git.writer_for(bundle)
    if writer is None:
        return {
            "committed": False,
            "pushed": False,
            "detail": "bundle is not inside a git repository (or git is unavailable)",
        }
    return writer.commit_and_push(paths, message, expected_branch=expected_branch)


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
    git: GitBackend | None = None,
    expected_branch: str | None = None,
) -> dict[str, Any]:
    """Create a concept via MCP, enforcing the richness floor.

    Forwards all recommended frontmatter (title/description/tags/resource/timestamp)
    plus arbitrary extension keys (``extra``) to ``core.templates.create_concept``.
    An explicit ``resource``/``timestamp`` arg overrides a same-named ``extra`` key.

    In draft write mode the concept additionally receives the OKF
    v0.2 trust fields ``status: draft`` and ``generated: {by: process:okf-mcp}``
    (caller-supplied values win — ``setdefault`` semantics), and the written
    file is committed and pushed; the git outcome is reported in the result's
    ``git`` key and never fails the create.
    """
    started_at = time.monotonic()
    ok = False
    git_outcome: dict[str, Any] | None = None
    try:
        if git is not None:
            if expected_branch is None:
                raise ValueError("draft writes require an explicit expected branch")
            git.require_branch(bundle, expected_branch)
        _check_richness(body)
        extra_fm: dict[str, Any] = dict(extra) if extra else {}
        if resource is not None:
            extra_fm["resource"] = resource
        if timestamp is not None:
            extra_fm["timestamp"] = timestamp
        if git is not None:
            # Provenance for the post-hoc review workflow: MCP-authored
            # concepts stay draft until a human flips status + adds verified.
            forbidden = {"verified", "trust"} & extra_fm.keys()
            if forbidden:
                raise ValueError(
                    "draft authoring rejects caller trust fields: "
                    + ", ".join(sorted(forbidden))
                )
            extra_fm["status"] = "draft"
            extra_fm["generated"] = {
                "by": "process:okf-mcp",
                "at": datetime.now(UTC).isoformat(),
            }
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
        ok = True
        result: dict[str, Any] = {"created": True, "cid": cid, "path": str(path)}
        git_outcome = _git_commit_result(
            git, bundle, [path], f"okf-mcp: create concept {cid}",
            expected_branch=expected_branch,
        )
        if git_outcome is not None:
            result["git"] = git_outcome
        return result
    finally:
        _log_tool_call(
            "create_concept",
            started_at,
            ok,
            bundle=bundle,
            cid=cid,
            type=type,
            committed=git_outcome.get("committed") if git_outcome else None,
            pushed=git_outcome.get("pushed") if git_outcome else None,
        )


def tool_init_bundle(
    reg: BundleRegistry,
    bundle: BundleName,
    okf_version: OkfVersion = "0.2",
    git: GitBackend | None = None,
    expected_branch: str | None = None,
) -> dict[str, Any]:
    """Initialize a bundle root via MCP (idempotent)."""
    started_at = time.monotonic()
    ok = False
    git_outcome: dict[str, Any] | None = None
    try:
        if git is not None:
            if expected_branch is None:
                raise ValueError("draft writes require an explicit expected branch")
            git.require_branch(bundle, expected_branch)
        path = init_bundle(reg.get(bundle), okf_version=okf_version)
        ok = True
        result: dict[str, Any] = {"initialized": True, "path": str(path)}
        git_outcome = _git_commit_result(
            git, bundle, [path], f"okf-mcp: init bundle {bundle}",
            expected_branch=expected_branch,
        )
        if git_outcome is not None:
            result["git"] = git_outcome
        return result
    finally:
        _log_tool_call(
            "init_bundle",
            started_at,
            ok,
            bundle=bundle,
            okf_version=okf_version,
            committed=git_outcome.get("committed") if git_outcome else None,
            pushed=git_outcome.get("pushed") if git_outcome else None,
        )


def tool_sync_status(
    reg: BundleRegistry,
    git: GitBackend,
    bundle: BundleName,
    *,
    write_mode: str = "disabled",
    lane: str = "stable",
    upstream_ref: str = "origin/main",
    expected_write_branch: str | None = None,
    git_commit: bool | None = None,
) -> dict[str, Any]:
    """Report a bundle's git provenance (sha/branch/dirty) for staleness checks."""
    if git_commit:
        write_mode = "draft"
        if lane == "stable":
            lane = "preview"
    started_at = time.monotonic()
    ok = False
    try:
        path = reg.get(bundle)
        writer = git.writer_for(bundle)
        result: dict[str, Any] = {
            "bundle": bundle,
            "path": str(path),
            "lane": lane,
            "write_mode": write_mode,
            "expected_write_branch": expected_write_branch,
            "git_commit": write_mode == "draft" if git_commit is None else git_commit,
            "tracked": writer is not None,
        }
        if writer is not None:
            result.update(writer.status(upstream_ref))
        ok = True
        return result
    finally:
        _log_tool_call("sync_status", started_at, ok, bundle=bundle)


def tool_list_bundles(reg: BundleRegistry) -> list[dict[str, Any]]:
    """List every registered bundle name and its resolved root path."""
    started_at = time.monotonic()
    ok = False
    names: list[str] = []
    try:
        names = reg.names()
        ok = True
        return [{"bundle": name, "path": str(reg.get(name))} for name in names]
    finally:
        _log_tool_call("list_bundles", started_at, ok, n_bundles=len(names))


def make_server(
    bundles: dict[str, Any] | list[tuple[str, Any]],
    *,
    host: str = "127.0.0.1",
    port: int = 4020,
    write_mode: str = "disabled",
    lane: str = "stable",
    expected_write_branch: str | None = None,
    upstream_ref: str = "origin/main",
    publication_profile: str | None = None,
    git_commit: bool | None = None,
) -> FastMCP:
    """Build a FastMCP server with tools + per-concept ``okf://`` resources.

    Args:
        bundles: Mapping of bundle name to bundle root path, or an ordered
            list of ``(name, path)`` pairs (the list form is required to
            detect a duplicate name — see :class:`BundleRegistry`).
        host: Bind address for HTTP/SSE transports (default loopback ``127.0.0.1``).
              Passed to :class:`FastMCP`; DNS-rebinding protection is enabled
              automatically for loopback addresses.
        port: TCP port for HTTP/SSE transports (default ``4020``, the hive OKF port band).
              Ignored in stdio mode but always forwarded to the constructor so a single
              ``make_server()`` call covers all transport choices.
        write_mode: ``disabled`` omits mutators; ``draft`` exposes them and
              commits successful writes from a preview checkout.
        lane: Authority lane reported by ``sync_status``. Draft mode requires preview.
        expected_write_branch: Required in draft mode and verified twice per write.
        upstream_ref: Ref compared with the served checkout for reconciliation.
        publication_profile: Optional governed-publication validation dialect.
        git_commit: Deprecated compatibility alias for draft/preview mode.
    """
    if write_mode not in {"disabled", "draft"}:
        raise ValueError("write_mode must be disabled or draft")
    if lane not in {"stable", "preview"}:
        raise ValueError("lane must be stable or preview")
    if publication_profile not in {None, "hive"}:
        raise ValueError("publication_profile must be hive when configured")
    if git_commit:
        write_mode = "draft"
        if lane == "stable":
            lane = "preview"
    if write_mode == "draft" and lane != "preview":
        raise ValueError("draft write mode requires the preview lane")
    if write_mode == "draft" and not expected_write_branch:
        raise ValueError("draft write mode requires expected_write_branch")
    reg = BundleRegistry(bundles)
    git = GitBackend(reg)
    write_git = git if write_mode == "draft" else None
    server = FastMCP("okf", host=host, port=port, streamable_http_path="/mcp")

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
        metadata: MetadataFilter = None,
        cursor: SearchCursor = None,
        response_version: SearchResponseVersion = "v1",
    ) -> dict[str, Any] | list[dict[str, Any]]:
        return tool_search(
            reg, bundle, query, type, tag, limit, metadata, cursor, response_version
        )

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
        direction: Direction = "both",
    ) -> str:
        return tool_read_concept(reg, bundle, concept_id, depth, token_budget, direction)

    @server.tool(
        name="graph_links",
        title="Traverse graph links",
        description=_GRAPH_DESC,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def _graph_links(
        bundle: BundleName,
        concept_id: ConceptId,
        direction: Direction = "both",
        relation: RelationFilter = None,
    ) -> dict[str, Any]:
        return tool_graph_links(reg, bundle, concept_id, direction, relation)

    @server.tool(
        name="validate",
        title="Validate bundle",
        description=_VALIDATE_DESC,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def _validate(bundle: BundleName) -> dict[str, Any]:
        return tool_validate(reg, bundle, publication_profile)

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
            reg,
            bundle,
            cid,
            type,
            title,
            description,
            body,
            tags,
            resource,
            timestamp,
            extra,
            git=write_git,
            expected_branch=expected_write_branch,
        )

    def _init_bundle(bundle: BundleName, okf_version: OkfVersion = "0.2") -> dict[str, Any]:
        return tool_init_bundle(
            reg, bundle, okf_version, git=write_git,
            expected_branch=expected_write_branch,
        )

    if write_mode == "draft":
        server.tool(
            name="create_concept",
            title="Create concept",
            description=_CREATE_DESC,
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, idempotentHint=False,
                openWorldHint=False,
            ),
        )(_create_concept)
        server.tool(
            name="init_bundle",
            title="Initialize bundle",
            description=_INIT_DESC,
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=True, idempotentHint=True,
                openWorldHint=False,
            ),
        )(_init_bundle)

    @server.tool(
        name="list_bundles",
        title="List registered bundles",
        description=_LIST_BUNDLES_DESC,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def _list_bundles() -> list[dict[str, Any]]:
        return tool_list_bundles(reg)

    @server.tool(
        name="sync_status",
        title="Bundle git provenance",
        description=_SYNC_STATUS_DESC,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    def _sync_status(bundle: BundleName) -> dict[str, Any]:
        return tool_sync_status(
            reg, git, bundle, write_mode=write_mode, lane=lane,
            upstream_ref=upstream_ref, expected_write_branch=expected_write_branch,
            git_commit=git_commit,
        )

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


def _parse_bundle_arg(raw: str) -> tuple[str, str]:
    """Parse one CLI bundle argument: either ``NAME=PATH`` or a bare ``PATH``.

    A bare path is registered under its directory basename (the original
    behavior — this is why a container mounting a bundle at ``/bundle``
    registers it as the not-very-meaningful name ``bundle``). ``NAME=PATH``
    lets a deployment give the bundle a real name independent of its mount
    point. Splitting on the first ``=`` is a convention, not a hard
    guarantee: ``=`` *is* a legal character in a POSIX path (though rare in
    practice for deployment mount points), so a bare path containing ``=``
    would be misparsed as ``NAME=PATH``. Bundles are expected to be named
    without ``=`` in this deployment; a directory that genuinely needs one
    should use the explicit ``NAME=PATH`` form to disambiguate.
    """
    if "=" in raw:
        name, _, path = raw.partition("=")
        name = name.strip()
        path = path.strip()
        if not name or not path:
            raise ValueError(f"invalid NAME=PATH bundle argument: {raw!r}")
        return name, path
    return Path(raw).name, raw


def main(argv: list[str] | None = None) -> int:
    import argparse

    _TRANSPORT_ALIASES = {"http": "streamable-http"}

    parser = argparse.ArgumentParser(
        prog="okf-mcp",
        description=(
            "OKF MCP server. Each bundle argument is either a bare directory path "
            "(registered under its directory basename) or an explicit NAME=PATH to name "
            "it independently of its mount point/directory name. "
            "Use --transport to select stdio (default), streamable-http, or sse."
        ),
    )
    parser.add_argument(
        "bundles",
        nargs="+",
        help=(
            "Bundle directories to serve — PATH (registered by directory basename) or "
            "NAME=PATH (registered under an explicit name)."
        ),
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http", "streamable-http", "sse"],
        help=(
            "Transport to use: stdio (default), streamable-http (or alias http), sse. "
            "HTTP transports bind --host:--port (loopback by default)."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for HTTP/SSE transports (default 127.0.0.1 — loopback only).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4020,
        help="Port for HTTP/SSE transports (default 4020 — hive OKF port band).",
    )
    parser.add_argument(
        "--write-mode",
        choices=["disabled", "draft"],
        default="disabled",
        help=(
            "Write policy: disabled omits mutating tools; draft exposes "
            "reviewed-preview authoring."
        ),
    )
    parser.add_argument(
        "--lane", choices=["stable", "preview"], default="stable",
        help="Authority lane reported by sync_status; draft writes require preview.",
    )
    parser.add_argument(
        "--expected-write-branch",
        help="Required with draft mode; every write verifies this branch before mutation.",
    )
    parser.add_argument(
        "--upstream-ref", default="origin/main",
        help="Git ref used to reconcile the served revision (default origin/main).",
    )
    parser.add_argument(
        "--publication-profile", choices=["hive"], default=None,
        help="Optional governed-publication validation profile.",
    )
    parser.add_argument(
        "--git-commit",
        action="store_true",
        help=(
            "DEPRECATED alias for --write-mode draft --lane preview; also requires "
            "--expected-write-branch. Commit and push each "
            "successful write (create_concept, init_bundle) into the "
            "git repository containing the bundle; MCP-created concepts get status: draft + "
            "generated: process:okf-mcp trust fields. Git failures degrade to warnings in "
            "the tool result — the file write itself is never rolled back."
        ),
    )
    args = parser.parse_args(argv)
    transport: str = _TRANSPORT_ALIASES.get(args.transport, args.transport)
    bundles = [_parse_bundle_arg(b) for b in args.bundles]
    if args.git_commit:
        print(
            "warning: --git-commit is deprecated; use --write-mode draft --lane preview "
            "--expected-write-branch BRANCH",
            file=sys.stderr,
        )
    server = make_server(
        bundles, host=args.host, port=args.port, write_mode=args.write_mode,
        lane=args.lane, expected_write_branch=args.expected_write_branch,
        upstream_ref=args.upstream_ref,
        publication_profile=args.publication_profile,
        git_commit=True if args.git_commit else None,
    )
    server.run(transport=transport)  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
