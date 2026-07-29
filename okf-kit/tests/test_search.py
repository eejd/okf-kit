"""Tests for okf_kit.core.search — inverted index + ranking (REQ-CONS-14..17, REQ-SRCH-01..04)."""
from __future__ import annotations

from pathlib import Path

from okf_kit.core.search import Hit, build_index, search


def _bundle(tmp_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_search_exact_title_ranks_first(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: Table\ntitle: Customer Orders\ndescription: x\n---\norders\n",
            "b.md": "---\ntype: Table\ntitle: Users\ndescription: customer\n---\nno orders here\n",
        },
    )
    hits = search(build_index(tmp_path), "Customer Orders")
    assert hits and hits[0].cid == "a"


def test_search_body_match(tmp_path):
    _bundle(
        tmp_path,
        {"a.md": "---\ntype: Note\ntitle: A\ndescription: d\n---\nThe widget joins the orders table.\n"},
    )
    hits = search(build_index(tmp_path), "widget")
    assert len(hits) == 1 and hits[0].cid == "a"


def test_search_type_filter(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: Table\ntitle: churn\ndescription: d\n---\nchurn\n",
            "b.md": "---\ntype: Metric\ntitle: churn rate\ndescription: d\n---\nchurn\n",
        },
    )
    hits = search(build_index(tmp_path), "churn", type=["Metric"])
    assert [h.cid for h in hits] == ["b"]


def test_search_tag_filter(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: x\ndescription: d\ntags: [pii]\n---\nalpha\n",
            "b.md": "---\ntype: T\ntitle: y\ndescription: d\ntags: [public]\n---\nalpha\n",
        },
    )
    hits = search(build_index(tmp_path), "alpha", tag=["pii"])
    assert [h.cid for h in hits] == ["a"]


def test_search_ranking_frontmatter_over_body(tmp_path):
    _bundle(
        tmp_path,
        {
            "in_title.md": "---\ntype: T\ntitle: Revenue Metric\ndescription: d\n---\nunrelated body\n",
            "in_body.md": "---\ntype: T\ntitle: Something\ndescription: d\n---\nrevenue revenue revenue\n",
        },
    )
    hits = search(build_index(tmp_path), "revenue")
    assert hits[0].cid == "in_title"  # title match outranks body-only match


def test_search_indexes_extension_frontmatter_generically(tmp_path):
    _bundle(
        tmp_path,
        {
            "code/service.md": (
                "---\n"
                "type: CodeModule\n"
                "title: Service\n"
                "description: Generated code map.\n"
                "source_path: gateway/src/service.py\n"
                "repo: gateway\n"
                "package: gateway-execution\n"
                "---\n"
                "No package name in body.\n"
            ),
            "notes/mention.md": (
                "---\n"
                "type: Note\n"
                "title: Mention\n"
                "description: Generated code map.\n"
                "---\n"
                "gateway-execution appears here in prose only.\n"
            ),
        },
    )
    hits = search(build_index(tmp_path), "gateway-execution")
    assert hits[0].cid == "code/service"


def test_search_limit(tmp_path):
    _bundle(tmp_path, {f"n{i}.md": "---\ntype: T\ntitle: item\ndescription: d\n---\nshared\n" for i in range(5)})
    assert len(search(build_index(tmp_path), "shared", limit=3)) == 3


def test_search_empty_query_returns_all(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: A\ndescription: d\n---\nx\n",
            "b.md": "---\ntype: T\ntitle: B\ndescription: d\n---\ny\n",
        },
    )
    assert [h.cid for h in search(build_index(tmp_path), "")] == ["a", "b"]


def test_search_no_match(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: T\ntitle: A\ndescription: d\n---\nx\n"})
    assert search(build_index(tmp_path), "zzzznomatch") == []


def test_search_snippet_contains_term(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: T\ntitle: A\ndescription: d\n---\nThe quick brown fox jumps.\n"})
    hits = search(build_index(tmp_path), "brown")
    assert hits and "brown" in hits[0].snippet.lower()


def test_search_hit_shape(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: Table\ntitle: A\ndescription: d\n---\nplaceholder\n"})
    h = search(build_index(tmp_path), "placeholder")[0]
    assert isinstance(h, Hit)
    assert h.type == "Table"


def test_search_common_term_ranks_below_rare_term(tmp_path):
    """IDF: a term present in nearly every doc should score far below one unique to a doc."""
    common = {f"common{i}.md": "---\ntype: T\ntitle: item\ndescription: d\n---\nwidget\n" for i in range(9)}
    _bundle(tmp_path, {**common, "rare.md": "---\ntype: T\ntitle: item\ndescription: d\n---\nzephyr\n"})
    index = build_index(tmp_path)
    common_hit = next(h for h in search(index, "widget") if h.cid == "common0")
    rare_hit = search(index, "zephyr")[0]
    assert rare_hit.score > common_hit.score


def test_search_stopwords_do_not_manufacture_confident_matches(tmp_path):
    """A query built mostly of stopwords plus one unrelated real word should not
    outscore a document that genuinely matches the query's only content word."""
    _bundle(
        tmp_path,
        {
            "unrelated.md": (
                "---\ntype: T\ntitle: Token Compression\ndescription: d\n---\n"
                "How do I use the token compression CLI? See the docs.\n"
            ),
            "relevant.md": (
                "---\ntype: T\ntitle: ZeroTier Token Rotation\ndescription: d\n---\n"
                "Rotate the ZeroTier API token via the Central API.\n"
            ),
        },
    )
    hits = search(build_index(tmp_path), "how do I rotate the ZeroTier API token")
    assert hits[0].cid == "relevant"


def test_search_stopwords_alone_return_no_hits(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: T\ntitle: A\ndescription: d\n---\nThe quick fox.\n"})
    assert search(build_index(tmp_path), "how do the a an") == []


def test_search_single_char_tokens_ignored(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: T\ntitle: I\ndescription: d\n---\nx\n"})
    # A bare "I" query should not match purely on the single-character token.
    assert search(build_index(tmp_path), "i") == []
