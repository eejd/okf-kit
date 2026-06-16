"""Tests for okf_kit.core.links — relative-link extraction, resolution,
path-containment guard (SECURITY), adjacency + backlinks.

REQ-CONS-10..13, SPEC §5.3.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_kit.core.links import (
    broken_links,
    build_adjacency,
    build_backlinks,
    cid_segments_valid,
    concept_outgoing,
    extract_link_targets,
    iter_concept_files,
    resolve_cid_path,
)
from okf_kit.core.parse import parse_concept


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _concept(root: Path, rel: str):
    return parse_concept(root / rel, root)


# --- cid validation + path containment (SECURITY) --------------------------


def test_cid_segments_valid():
    assert cid_segments_valid("tables/users")
    assert cid_segments_valid("a")
    assert cid_segments_valid("tables/v2/user.info")
    assert not cid_segments_valid("")
    assert not cid_segments_valid("../etc/passwd")
    assert not cid_segments_valid("/etc/passwd")
    assert not cid_segments_valid("tables/../etc")
    assert not cid_segments_valid("tables/ users")  # space is invalid in a segment


def test_resolve_cid_path_basic_and_missing(tmp_path):
    _write(tmp_path, "tables/users.md", "---\ntype: Table\n---\nx\n")
    assert resolve_cid_path(tmp_path, "tables/users") == (tmp_path / "tables/users.md")
    assert resolve_cid_path(tmp_path, "nonexistent/thing") is None


@pytest.mark.parametrize("cid", ["../../etc/passwd", "/etc/passwd", "tables/../etc/x"])
def test_resolve_cid_path_rejects_traversal(tmp_path, cid):
    assert resolve_cid_path(tmp_path, cid) is None


def test_resolve_cid_path_symlink_escape_rejected(tmp_path):
    outside = tmp_path.parent / "_okf_symlink_escape.md"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "tables" / "escape.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not supported on this filesystem")
    try:
        # symlink resolves OUTSIDE the bundle root -> must be rejected
        assert resolve_cid_path(tmp_path, "tables/escape") is None
    finally:
        if link.is_symlink() or link.exists():
            link.unlink()
        if outside.exists():
            outside.unlink()


# --- extract_link_targets --------------------------------------------------


def test_extract_link_targets_filters_external_and_absolute():
    body = "[a](a.md) [b](b.md#x) [ext](https://e.com/y.md) [abs](/z.md) plain"
    assert extract_link_targets(body) == ["a.md", "b.md"]


# --- concept_outgoing ------------------------------------------------------


def test_concept_outgoing_resolves_relative_and_parent(tmp_path):
    _write(
        tmp_path,
        "tables/users.md",
        "---\ntype: Table\n---\nSee [orders](../orders.md) and [churn](../metrics/churn.md).\n",
    )
    _write(tmp_path, "orders.md", "---\ntype: Table\n---\norders\n")
    _write(tmp_path, "metrics/churn.md", "---\ntype: Metric\n---\nchurn\n")
    c = _concept(tmp_path, "tables/users.md")
    assert concept_outgoing(tmp_path, c) == ["metrics/churn", "orders"]


def test_concept_outgoing_drops_nonexistent(tmp_path):
    _write(tmp_path, "a.md", "---\ntype: T\n---\n[ghost](ghost.md) [b](b.md)\n")
    _write(tmp_path, "b.md", "---\ntype: T\n---\nb\n")
    assert concept_outgoing(tmp_path, _concept(tmp_path, "a.md")) == ["b"]


def test_concept_outgoing_excludes_external_absolute_index(tmp_path):
    a_body = "---\ntype: T\n---\n[ext](https://x/y.md) [abs](/b.md) [idx](index.md) [rel](b.md)\n"
    _write(tmp_path, "a.md", a_body)
    _write(tmp_path, "b.md", "---\ntype: T\n---\nb\n")
    _write(tmp_path, "index.md", "# idx\n")
    assert concept_outgoing(tmp_path, _concept(tmp_path, "a.md")) == ["b"]


def test_concept_outgoing_strips_fragment_and_dedups(tmp_path):
    _write(tmp_path, "a.md", "---\ntype: T\n---\n[b](b.md#s1) again [b](b.md#s2)\n")
    _write(tmp_path, "b.md", "---\ntype: T\n---\nb\n")
    assert concept_outgoing(tmp_path, _concept(tmp_path, "a.md")) == ["b"]


def test_concept_outgoing_escape_dropped(tmp_path):
    _write(tmp_path, "a.md", "---\ntype: T\n---\n[out](../outside.md)\n")
    assert concept_outgoing(tmp_path, _concept(tmp_path, "a.md")) == []


# --- adjacency + backlinks -------------------------------------------------


def test_build_adjacency_and_backlinks(tmp_path):
    for rel in ("a.md", "b.md", "c.md"):
        _write(tmp_path, rel, "---\ntype: T\n---\n\n")
    _write(tmp_path, "a.md", "---\ntype: T\n---\n[b](b.md)\n")
    _write(tmp_path, "b.md", "---\ntype: T\n---\n[c](c.md)\n")
    concepts = [parse_concept(tmp_path / r, tmp_path) for r in ("a.md", "b.md", "c.md")]
    adj = build_adjacency(tmp_path, concepts)
    assert adj == {"a": ["b"], "b": ["c"], "c": []}
    back = build_backlinks(adj)
    assert back == {"a": [], "b": ["a"], "c": ["b"]}


def test_adjacency_skips_reserved_files(tmp_path):
    _write(tmp_path, "a.md", "---\ntype: T\n---\n[b](b.md)\n")
    _write(tmp_path, "b.md", "---\ntype: T\n---\nb\n")
    _write(tmp_path, "index.md", "- [a](a.md)\n- [b](b.md)\n")  # reserved, not a node
    concepts = [parse_concept(tmp_path / r, tmp_path) for r in ("a.md", "b.md", "index.md")]
    adj = build_adjacency(tmp_path, concepts)
    assert set(adj) == {"a", "b"}


def test_broken_links_detection(tmp_path):
    _write(
        tmp_path, "a.md", "---\ntype: T\n---\n[ok](b.md) [ghost](ghost.md) [out](../outside.md)\n"
    )
    _write(tmp_path, "b.md", "---\ntype: T\n---\nb\n")
    c = parse_concept(tmp_path / "a.md", tmp_path)
    assert broken_links(tmp_path, c) == ["ghost.md", "../outside.md"]


def test_iter_concept_files_skips_symlink_escape(tmp_path):
    outside = tmp_path.parent / "_okf_walk_escape.md"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "evil.md"
    legit = tmp_path / "real.md"
    legit.write_text("---\ntype: T\n---\nx\n", encoding="utf-8")
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not supported")
    try:
        names = [p.name for p in iter_concept_files(tmp_path)]
        assert "real.md" in names
        assert "evil.md" not in names  # symlink escapes the bundle root
    finally:
        if link.is_symlink() or link.exists():
            link.unlink()
        if outside.exists():
            outside.unlink()
