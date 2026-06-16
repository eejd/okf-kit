"""Relative-link extraction, resolution, and the path-containment guard.

Builds the OKF knowledge-graph edges from **relative** Markdown links
(REQ-CONS-10..13, SPEC §5.3). External (``://``) and absolute (leading ``/``)
links are not edges in v0.1; broken and out-of-bundle links are dropped
silently.

SECURITY: every caller-supplied concept id and every link target is resolved
and confined to the bundle root. ``..`` traversal, absolute paths, and symlink
escapes cannot read files outside the root. Defense in depth — segment-regex
validation rejects ``..``/``/`` lexically, and a resolved-path containment
check rejects anything that escapes (including symlinks).
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from okf_kit.core.model import Concept

_LINK_RE = re.compile(r"\]\(([^)\s]+\.md)(?:#[A-Za-z0-9_-]*)?\)")
# A single path segment per SPEC §2.2.
_SEGMENT_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_RESERVED_FILES = frozenset({"index.md", "log.md"})


def is_external_target(target: str) -> bool:
    """External link (``://``), per SPEC §3.2 — not an internal edge."""
    return "://" in target


def is_absolute_target(target: str) -> bool:
    """Bundle-absolute link (leading ``/``) — not a *relative* edge in v0.1."""
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
    """Raw relative ``.md`` link targets found in ``body`` (pre-resolution).

    External and absolute targets are excluded.
    """
    targets: list[str] = []
    for match in _LINK_RE.finditer(body):
        target = match.group(1)
        if is_external_target(target) or is_absolute_target(target):
            continue
        targets.append(target)
    return targets


def concept_outgoing(root: Path, concept: Concept) -> list[str]:
    """Concept ids this concept links to (existing, non-reserved), deduped + sorted."""
    root_resolved = Path(root).resolve()
    src_dir = concept.path.parent.resolve()
    seen: set[str] = set()
    outgoing: list[str] = []
    for target in extract_link_targets(concept.body):
        resolved = (src_dir / target).resolve()
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
        resolved = (src_dir / target).resolve()
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
