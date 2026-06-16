"""Progressive context loader (REQ-AGT-07/08, design §7).

``read_concept(cid, depth=0)`` returns one concept; ``depth>0`` walks the
relative-link neighborhood in BFS order and concatenates Markdown within a
token budget. Deterministic (BFS + alphabetical tiebreak), cycle-safe, with a
trailing marker naming anything omitted.
"""
from __future__ import annotations

from pathlib import Path

from okf_kit.core.links import build_adjacency, iter_concept_files, resolve_cid_path
from okf_kit.core.model import Concept
from okf_kit.core.parse import parse_concept
from okf_kit.core.search import build_index, search

_CHARS_PER_TOKEN = 4


class ConceptNotFound(KeyError):
    """Raised when a concept id does not resolve to an existing concept."""

    def __init__(self, cid: str, suggestions: list[str]):
        self.cid = cid
        self.suggestions = suggestions
        hint = f" (did you mean: {', '.join(suggestions[:5])}?)" if suggestions else ""
        super().__init__(f"concept not found: {cid}{hint}")


def read_concept(
    root: Path, cid: str, depth: int = 0, token_budget: int = 8000
) -> str:
    """Read one concept, or a depth-N neighborhood as concatenated Markdown.

    ``depth=0`` returns the raw file content. ``depth>0`` returns the seed
    (always in full) plus its N-hop neighbors in BFS order, each under a
    ``# <cid> (depth k)`` header, truncated to ``token_budget`` with a marker.
    """
    root = Path(root).resolve()
    seed_path = resolve_cid_path(root, cid)
    if seed_path is None:
        raise ConceptNotFound(cid, _suggest(root, cid))
    if depth <= 0:
        return seed_path.read_text(encoding="utf-8")

    concepts = _load_concepts(root)
    by_cid = {c.cid: c for c in concepts}
    adjacency = build_adjacency(root, concepts)

    levels = _bfs_levels(cid, adjacency, depth)

    parts: list[str] = [
        f"<!-- okf context: seed={cid} depth={depth} token_budget={token_budget} -->\n\n"
    ]
    budget_used = _estimate(parts[0])

    seed_block = f"# {cid} (seed)\n\n{seed_path.read_text(encoding='utf-8')}\n\n"
    parts.append(seed_block)
    budget_used += _estimate(seed_block)

    omitted: list[str] = []
    for level_idx in range(1, len(levels)):
        for nb in levels[level_idx]:
            concept = by_cid.get(nb)
            if concept is None:
                continue
            block = f"# {nb} (depth {level_idx})\n\n{concept.path.read_text(encoding='utf-8')}\n\n"
            cost = _estimate(block)
            if budget_used + cost > token_budget:
                omitted.append(nb)
                continue
            parts.append(block)
            budget_used += cost

    if omitted:
        preview = ", ".join(omitted[:10])
        more = " …" if len(omitted) > 10 else ""
        word = "concept" if len(omitted) == 1 else "concepts"
        parts.append(
            f"… ({len(omitted)} {word} omitted to fit token_budget={token_budget}: "
            f"{preview}{more} — raise depth or token_budget, or read each).\n"
        )
    return "".join(parts)


def _bfs_levels(seed: str, adjacency: dict[str, list[str]], depth: int) -> list[list[str]]:
    levels: list[list[str]] = [[seed]]
    visited: set[str] = {seed}
    current = [seed]
    for _ in range(depth):
        nxt: list[str] = []
        for node in current:
            for nb in adjacency.get(node, []):
                if nb not in visited:
                    visited.add(nb)
                    nxt.append(nb)
        if not nxt:
            break
        levels.append(sorted(nxt))
        current = nxt
    return levels


def _load_concepts(root: Path) -> list[Concept]:
    concepts: list[Concept] = []
    for md in iter_concept_files(root):
        concept = parse_concept(md, root)
        if concept.reserved is None:
            concepts.append(concept)
    return concepts


def _suggest(root: Path, cid: str) -> list[str]:
    last = cid.rsplit("/", 1)[-1] or cid
    return [hit.cid for hit in search(build_index(root), last, limit=5)]


def _estimate(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN
