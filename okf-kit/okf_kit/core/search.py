"""Full-text search over an OKF bundle (REQ-CONS-14..17, REQ-SRCH-01..04).

Lightweight inverted index + weighted ranking (exact title > frontmatter >
body), no external deps. Filters by ``type`` and ``tag``. Deterministic order
(score desc, then cid asc). A future BM25/IDF ranker can swap in behind the
same :func:`search` signature.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from okf_kit.core.links import iter_concept_files
from okf_kit.core.parse import parse_concept

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WEIGHTS = {"title": 5, "tag": 4, "type": 3, "description": 2, "body": 1}
_EXACT_TITLE_BOOST = 100.0


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _fm_str(fm: dict[str, Any], key: str) -> str:
    value = fm.get(key)
    return value if isinstance(value, str) else ""


def _fm_str_list(fm: dict[str, Any], key: str) -> list[str]:
    value = fm.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@dataclass
class Hit:
    cid: str
    title: str
    type: str
    snippet: str
    score: float


@dataclass
class _Doc:
    cid: str
    title: str
    type: str
    tags: list[str]
    description: str
    body: str
    title_terms: Counter[str]
    tag_terms: Counter[str]
    type_terms: Counter[str]
    desc_terms: Counter[str]
    body_terms: Counter[str]


@dataclass
class Index:
    docs: list[_Doc] = field(default_factory=list)

    def to_dict(self) -> list[dict[str, Any]]:
        return [
            {"cid": d.cid, "title": d.title, "type": d.type, "tags": d.tags}
            for d in self.docs
        ]


def build_index(root: Path) -> Index:
    """Build a search index over all non-reserved concepts under ``root``."""
    root = Path(root).resolve()
    docs: list[_Doc] = []
    for md in iter_concept_files(root):
        concept = parse_concept(md, root)
        if concept.reserved is not None:
            continue
        title = _fm_str(concept.frontmatter, "title")
        type_value = _fm_str(concept.frontmatter, "type")
        description = _fm_str(concept.frontmatter, "description")
        tags = _fm_str_list(concept.frontmatter, "tags")
        docs.append(
            _Doc(
                cid=concept.cid,
                title=title,
                type=type_value,
                tags=tags,
                description=description,
                body=concept.body,
                title_terms=Counter(_tokenize(title)),
                tag_terms=Counter(_tokenize(" ".join(tags))),
                type_terms=Counter(_tokenize(type_value)),
                desc_terms=Counter(_tokenize(description)),
                body_terms=Counter(_tokenize(concept.body)),
            )
        )
    return Index(docs=docs)


def search(
    index: Index,
    q: str,
    type: list[str] | None = None,
    tag: list[str] | None = None,
    limit: int = 20,
) -> list[Hit]:
    """Ranked search. Empty ``q`` returns all concepts (filtered), by cid."""
    q_terms = _tokenize(q)
    norm_query = q.strip().lower()
    type_filter = set(type) if type else None
    tag_filter = set(tag) if tag else None

    hits: list[Hit] = []
    for doc in index.docs:
        if type_filter is not None and doc.type not in type_filter:
            continue
        if tag_filter is not None and not (set(doc.tags) & tag_filter):
            continue
        score = _score(norm_query, q_terms, doc)
        if q_terms and score <= 0:
            continue
        hits.append(
            Hit(
                cid=doc.cid,
                title=doc.title or doc.cid,
                type=doc.type,
                snippet=_snippet(q_terms, doc),
                score=score,
            )
        )
    hits.sort(key=lambda h: (-h.score, h.cid))
    return hits[:limit]


def _score(norm_query: str, q_terms: list[str], doc: _Doc) -> float:
    if not q_terms:
        return 0.0
    score = 0.0
    if norm_query and doc.title.strip().lower() == norm_query:
        score += _EXACT_TITLE_BOOST
    for term in q_terms:
        tf = (
            doc.title_terms.get(term, 0) * _WEIGHTS["title"]
            + doc.tag_terms.get(term, 0) * _WEIGHTS["tag"]
            + doc.type_terms.get(term, 0) * _WEIGHTS["type"]
            + doc.desc_terms.get(term, 0) * _WEIGHTS["description"]
            + doc.body_terms.get(term, 0) * _WEIGHTS["body"]
        )
        score += tf
    return float(score)


def _snippet(q_terms: list[str], doc: _Doc) -> str:
    text = doc.body.strip()
    if not text:
        text = doc.description.strip()
    if not text:
        return ""
    lower = text.lower()
    positions = [lower.find(t) for t in q_terms if t and t in lower]
    if positions:
        center = min(positions)
        start = max(0, center - 40)
        end = min(len(text), center + 40)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(text) else ""
        return prefix + text[start:end] + suffix
    return text[:80] + ("…" if len(text) > 80 else "")
