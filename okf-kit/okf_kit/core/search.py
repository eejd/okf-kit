"""Full-text search over an OKF bundle (REQ-CONS-14..17, REQ-SRCH-01..04).

Lightweight inverted index + weighted, IDF-scaled ranking (exact title >
frontmatter > body), no external deps. Filters by ``type`` and ``tag``.
Deterministic order (score desc, then cid asc).

Ranking model: for each query term, the per-field weighted term frequency is
multiplied by a smoothed inverse-document-frequency factor — terms that occur
in most of the bundle carry little weight, however often they repeat, so a
term unique to one document dominates a term present nearly everywhere. A
term that occurs in literally every concept degenerates to weight 1 (a small
floor, never zero) and cannot manufacture a hit on its own. Common English
stopwords and single-character tokens are dropped before indexing or scoring
— otherwise IDF alone is not enough: a stopword can have a *low* document
frequency by coincidence (e.g. a rare pronoun or an abbreviation fragment)
and still contribute a large, meaningless score.

Per-document length is tracked in the index (:attr:`_Doc.length`,
:attr:`Index.avg_length`) but is deliberately **not** used to normalize
scores: an earlier BM25-style length pivot was tried and reverted — it
systematically rewards short, keyword-stuffed documents over longer,
genuinely relevant ones (a short note repeating a query term once scores
higher, post-normalization, than a real match diluted across a longer body),
which is the opposite of what this ranker should do. The length data is kept
for external instrumentation (does the bundle skew toward very long or very
short concepts over time?), not for scoring.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from okf_kit.core.links import iter_concept_files
from okf_kit.core.parse import parse_concept

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WEIGHTS = {"title": 5, "tag": 4, "frontmatter": 3, "type": 3, "description": 2, "body": 1}
_EXACT_TITLE_BOOST = 100.0
# Minimum token length to carry search weight. Single characters (stray "i", "a",
# fragments of "e.g."/"i.e.") are near-never a meaningful search term in prose.
_MIN_TOKEN_LEN = 2
# A small, deliberately short stopword list: common function words that would
# otherwise occasionally earn a nontrivial IDF by coincidence (e.g. "do" or "i"
# appearing in only a handful of concepts) and manufacture a confident-looking
# but meaningless match. Not exhaustive — this is a precision floor, not a
# linguistic stopword corpus.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "am", "be", "been", "being", "was", "were",
        "do", "does", "did", "doing", "have", "has", "had", "having",
        "how", "what", "when", "where", "why", "who", "which", "whom",
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
        "my", "your", "his", "its", "our", "their",
        "of", "to", "in", "on", "at", "for", "with", "by", "from", "as", "into", "about",
        "that", "this", "these", "those", "and", "or", "but", "if", "so", "not", "no",
        "can", "could", "should", "would", "may", "might", "must", "shall", "will",
        "up", "down", "out", "off", "over", "under", "again", "then", "once", "here", "there",
    }
)


def _tokenize(text: str) -> list[str]:
    return [
        t
        for t in _TOKEN_RE.findall(text.lower())
        if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS
    ]


def _fm_str(fm: dict[str, Any], key: str) -> str:
    value = fm.get(key)
    return value if isinstance(value, str) else ""


def _fm_str_list(fm: dict[str, Any], key: str) -> list[str]:
    value = fm.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _frontmatter_text(fm: dict[str, Any]) -> str:
    values: list[str] = []
    for value in fm.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(item for item in value if isinstance(item, str))
    return " ".join(values)


@dataclass
class Hit:
    """Ranked search result.

    Attributes:
        cid: Concept id for the hit.
        title: Display title, falling back to the concept id when missing.
        type: OKF concept type.
        snippet: Short matching text excerpt.
        score: Weighted ranking score.
    """

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
    frontmatter_terms: Counter[str]
    body_terms: Counter[str]
    length: int = 0
    """Total term occurrences across all fields; tracked for external bundle
    instrumentation only — not used in scoring (see module docstring)."""


@dataclass
class Index:
    """In-memory search index for one OKF bundle.

    Attributes:
        docs: Indexed concept documents.
        doc_freq: Number of documents containing each term at least once.
        avg_length: Mean :attr:`_Doc.length` across ``docs`` (0.0 if empty).
    """

    docs: list[_Doc] = field(default_factory=list)
    doc_freq: Counter[str] = field(default_factory=Counter)
    avg_length: float = 0.0

    def to_dict(self) -> list[dict[str, Any]]:
        """Serialize index metadata for diagnostics.

        Returns:
            List of public concept metadata dictionaries.
        """

        return [
            {"cid": d.cid, "title": d.title, "type": d.type, "tags": d.tags}
            for d in self.docs
        ]

    def idf(self, term: str) -> float:
        """Smoothed inverse document frequency for ``term``.

        Ranges from ``1.0`` (term present in every document — carries no
        discriminating weight) up to ``log(n_docs + 1) + 1`` (term unique to
        one document). Never negative or zero, so a ubiquitous term still
        contributes something but cannot dominate a rarer one.
        """

        n = len(self.docs)
        if n == 0:
            return 1.0
        df = self.doc_freq.get(term, 0)
        return math.log((n + 1) / (df + 1)) + 1.0


def _doc_terms(doc: _Doc) -> set[str]:
    terms: set[str] = set()
    for counter in (
        doc.title_terms,
        doc.tag_terms,
        doc.type_terms,
        doc.desc_terms,
        doc.frontmatter_terms,
        doc.body_terms,
    ):
        terms.update(counter)
    return terms


def build_index(root: Path) -> Index:
    """Build a search index over a bundle.

    Args:
        root: OKF bundle root.

    Returns:
        In-memory index of all non-reserved concepts under ``root``.
    """

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
        title_terms = Counter(_tokenize(title))
        tag_terms = Counter(_tokenize(" ".join(tags)))
        type_terms = Counter(_tokenize(type_value))
        desc_terms = Counter(_tokenize(description))
        frontmatter_terms = Counter(_tokenize(_frontmatter_text(concept.frontmatter)))
        body_terms = Counter(_tokenize(concept.body))
        length = sum(
            sum(c.values())
            for c in (title_terms, tag_terms, type_terms, desc_terms, frontmatter_terms, body_terms)
        )
        docs.append(
            _Doc(
                cid=concept.cid,
                title=title,
                type=type_value,
                tags=tags,
                description=description,
                body=concept.body,
                title_terms=title_terms,
                tag_terms=tag_terms,
                type_terms=type_terms,
                desc_terms=desc_terms,
                frontmatter_terms=frontmatter_terms,
                body_terms=body_terms,
                length=length,
            )
        )
    doc_freq: Counter[str] = Counter()
    for doc in docs:
        doc_freq.update(_doc_terms(doc))
    avg_length = (sum(d.length for d in docs) / len(docs)) if docs else 0.0
    return Index(docs=docs, doc_freq=doc_freq, avg_length=avg_length)


def search(
    index: Index,
    q: str,
    type: list[str] | None = None,
    tag: list[str] | None = None,
    limit: int = 20,
) -> list[Hit]:
    """Search an OKF index.

    Args:
        index: Search index built by ``build_index``.
        q: Query string. A blank (whitespace-only) query returns all filtered
            concepts by id. A non-blank query that reduces to no scorable
            terms after stopword/short-token filtering (e.g. "how do the")
            is a real query that matched nothing — it returns no hits, not
            every concept.
        type: Optional allowed concept types.
        tag: Optional required tag set; any matching tag qualifies.
        limit: Maximum number of hits to return.

    Returns:
        Ranked hits sorted by score descending, then concept id.
    """

    norm_query = q.strip().lower()
    q_terms = _tokenize(q)
    is_blank_query = not norm_query
    no_scorable_terms = bool(norm_query) and not q_terms
    type_filter = set(type) if type else None
    tag_filter = set(tag) if tag else None

    if no_scorable_terms:
        return []

    hits: list[Hit] = []
    for doc in index.docs:
        if type_filter is not None and doc.type not in type_filter:
            continue
        if tag_filter is not None and not (set(doc.tags) & tag_filter):
            continue
        score = _score(index, norm_query, q_terms, doc)
        if not is_blank_query and score <= 0:
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


def _score(index: Index, norm_query: str, q_terms: list[str], doc: _Doc) -> float:
    if not q_terms:
        return 0.0
    score = 0.0
    if norm_query and doc.title.strip().lower() == norm_query:
        score += _EXACT_TITLE_BOOST
    for term in q_terms:
        idf = index.idf(term)
        tf = (
            doc.title_terms.get(term, 0) * _WEIGHTS["title"]
            + doc.tag_terms.get(term, 0) * _WEIGHTS["tag"]
            + doc.type_terms.get(term, 0) * _WEIGHTS["type"]
            + doc.desc_terms.get(term, 0) * _WEIGHTS["description"]
            + doc.frontmatter_terms.get(term, 0) * _WEIGHTS["frontmatter"]
            + doc.body_terms.get(term, 0) * _WEIGHTS["body"]
        )
        if tf <= 0:
            continue
        score += tf * idf
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
