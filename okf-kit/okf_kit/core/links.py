"""Relative-link extraction, resolution, and the path-containment guard.

Builds the OKF knowledge-graph edges from **relative AND absolute
(bundle-relative)** Markdown links (SPEC §5). External (``://``) links are not
edges; broken and out-of-bundle links are dropped silently (SPEC §5.3).

SECURITY: every caller-supplied concept id and every link target is resolved
and confined to the bundle root. ``..`` traversal, absolute paths, and symlink
escapes cannot read files outside the root. Defense in depth — segment-regex
validation rejects ``..``/``/`` lexically, and a resolved-path containment
check rejects anything that escapes (including symlinks).
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from okf_kit.core.model import Concept

_LINK_RE = re.compile(r"\]\(([^)\s]+\.md)(?:#[A-Za-z0-9_-]*)?\)")
_OKF_LINK_RE = re.compile(
    r"\]\((okf://.+?/concepts/[^)\s#]+\.md)(?:#[A-Za-z0-9_-]*)?\)"
)
_RELATION_KEYS = frozenset(
    {"related", "governs", "implements", "depends-on", "evidence-for", "supersedes"}
)
# A single path segment per SPEC §2.2.
_SEGMENT_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_RESERVED_FILES = frozenset({"index.md", "log.md"})


@dataclass(frozen=True, order=True)
class GraphEdge:
    """One typed, addressable OKF graph edge."""

    source_bundle: str
    source_cid: str
    relation: str
    target_bundle: str
    target_cid: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": f"okf://{self.source_bundle}/concepts/{self.source_cid}.md",
            "source_bundle": self.source_bundle,
            "source_cid": self.source_cid,
            "relation": self.relation,
            "target": f"okf://{self.target_bundle}/concepts/{self.target_cid}.md",
            "target_bundle": self.target_bundle,
            "target_cid": self.target_cid,
        }


def is_external_target(target: str) -> bool:
    """External link (``://``), per SPEC §3.2 — not an internal edge."""
    return "://" in target


def is_absolute_target(target: str) -> bool:
    """Bundle-absolute link (leading ``/``) — resolved against the bundle root (SPEC §5.1)."""
    return target.startswith("/")


def cid_segments_valid(cid: str) -> bool:
    """True if every path segment of ``cid`` matches the SPEC §2.2 regex."""
    if not cid:
        return False
    return all(bool(_SEGMENT_RE.fullmatch(seg)) for seg in cid.split("/"))


def is_within(path: Path, root: Path) -> bool:
    """True if ``path`` is inside ``root`` (both should be resolved)."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def iter_concept_files(root: Path) -> Iterator[Path]:
    """Yield resolved, in-bundle ``.md`` paths — symlink escapes and dupes skipped.

    Centralizes the safe enumeration used by validate/search/context/index/mcp,
    so a symlinked ``.md`` that resolves outside the bundle is never read or
    written through.
    """
    root_resolved = Path(root).resolve()
    seen: set[str] = set()
    for candidate in sorted(root_resolved.rglob("*.md")):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not is_within(resolved, root_resolved):
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        yield resolved


def resolve_cid_path(root: Path, cid: str) -> Path | None:
    """Resolve a concept id to an existing ``.md`` path contained in ``root``.

    Returns ``None`` if the id is malformed, escapes the root (incl. symlink
    escapes), or does not point to an existing file.
    """
    root_resolved = Path(root).resolve()
    if not cid_segments_valid(cid):
        return None
    candidate = (root_resolved / f"{cid}.md").resolve()
    if not is_within(candidate, root_resolved):
        return None
    if not candidate.is_file():
        return None
    return candidate


def extract_link_targets(body: str) -> list[str]:
    """Raw ``.md`` link targets in ``body`` (relative + absolute), pre-resolution.

    External (``://``) targets are excluded; relative and bundle-absolute
    (leading ``/``) targets are both kept as graph edges (SPEC §5).
    """
    targets: list[str] = []
    for match in _LINK_RE.finditer(body):
        target = match.group(1)
        if is_external_target(target):
            continue
        targets.append(target)
    return targets


def parse_okf_uri(value: str) -> tuple[str, str] | None:
    """Parse ``okf://BUNDLE/concepts/CID.md`` into its address components."""
    match = re.fullmatch(r"okf://(.+?)/concepts/(.+)\.md", value)
    if match is None:
        return None
    bundle, cid = match.groups()
    if not cid_segments_valid(bundle) or not cid_segments_valid(cid):
        return None
    return bundle, cid


def _local_relation_target(root: Path, concept: Concept, value: str) -> str | None:
    """Resolve a local relation value with the same containment rules as Markdown links."""
    if value.endswith(".md"):
        resolved = _resolve_target(value, concept.path.parent.resolve(), Path(root).resolve())
        if not is_within(resolved, Path(root).resolve()):
            return None
        try:
            rel = resolved.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return None
        cid = rel.removesuffix(".md")
        return cid if cid_segments_valid(cid) else None
    return value if cid_segments_valid(value) else None


def concept_graph_edges(root: Path, concept: Concept, bundle: str) -> list[GraphEdge]:
    """Extract local Markdown links and typed frontmatter relations.

    Cross-bundle edges use the canonical ``okf://`` URI form. Local relation
    values may be concept ids or bundle-absolute/relative ``.md`` paths.
    """
    edges: set[GraphEdge] = set()
    for target in concept_outgoing(root, concept):
        edges.add(GraphEdge(bundle, concept.cid, "link", bundle, target))
    for uri in _OKF_LINK_RE.findall(concept.body):
        parsed = parse_okf_uri(uri)
        if parsed:
            edges.add(GraphEdge(bundle, concept.cid, "link", parsed[0], parsed[1]))
    for relation in _RELATION_KEYS:
        raw: Any = concept.frontmatter.get(relation)
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if not isinstance(value, str):
                continue
            parsed = parse_okf_uri(value)
            if parsed:
                edges.add(GraphEdge(bundle, concept.cid, relation, parsed[0], parsed[1]))
                continue
            local_target = _local_relation_target(root, concept, value)
            if local_target is not None:
                edges.add(GraphEdge(bundle, concept.cid, relation, bundle, local_target))
    return sorted(edges)


def _resolve_target(target: str, src_dir: Path, root: Path) -> Path:
    """Resolve a link target: absolute (leading ``/``) against the bundle root,
    relative against the source document's directory (SPEC §5.1/§5.2)."""
    if is_absolute_target(target):
        return (root / target.lstrip("/")).resolve()
    return (src_dir / target).resolve()


def concept_outgoing(root: Path, concept: Concept) -> list[str]:
    """Concept ids this concept links to (existing, non-reserved), deduped + sorted."""
    root_resolved = Path(root).resolve()
    src_dir = concept.path.parent.resolve()
    seen: set[str] = set()
    outgoing: list[str] = []
    for target in extract_link_targets(concept.body):
        resolved = _resolve_target(target, src_dir, root_resolved)
        if not is_within(resolved, root_resolved):
            continue
        if not resolved.is_file():
            continue  # drop non-existent silently (SPEC §5.3)
        if resolved.name in _RESERVED_FILES:
            continue  # reserved files are not concept nodes
        try:
            rel = resolved.relative_to(root_resolved).as_posix()
        except ValueError:
            continue
        cid = rel[:-3] if rel.endswith(".md") else rel
        if cid not in seen:
            seen.add(cid)
            outgoing.append(cid)
    return sorted(outgoing)


def broken_links(root: Path, concept: Concept) -> list[str]:
    """Raw relative targets that don't resolve to an existing in-bundle file.

    Broken links are tolerated (SPEC §5.3) — the validator reports them as
    warnings, not errors.
    """
    root_resolved = Path(root).resolve()
    src_dir = concept.path.parent.resolve()
    seen: set[str] = set()
    broken: list[str] = []
    for target in extract_link_targets(concept.body):
        if target in seen:
            continue
        resolved = _resolve_target(target, src_dir, root_resolved)
        if not is_within(resolved, root_resolved) or not resolved.is_file():
            seen.add(target)
            broken.append(target)
    return broken


def build_adjacency(root: Path, concepts: list[Concept]) -> dict[str, list[str]]:
    """``cid -> sorted outgoing concept ids`` for all non-reserved concepts."""
    return {
        concept.cid: concept_outgoing(root, concept)
        for concept in concepts
        if concept.reserved is None
    }


def build_backlinks(adjacency: dict[str, list[str]]) -> dict[str, list[str]]:
    """``cid -> sorted list of cids linking to it`` (REQ-CONS-13).

    Every node in ``adjacency`` is a key (empty list if nothing links to it).
    """
    back: dict[str, list[str]] = {cid: [] for cid in adjacency}
    for src, targets in adjacency.items():
        for target in targets:
            if target in back:
                back[target].append(src)
    return {cid: sorted(sources) for cid, sources in back.items()}
