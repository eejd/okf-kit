"""Tests for okf_kit.core.context — progressive-context loader (REQ-AGT-07/08, design §7)."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_kit.core.context import ConceptNotFound, read_concept


def _bundle(tmp_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_read_concept_depth0_returns_raw(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: T\ntitle: A\n---\nbody of a\n"})
    assert read_concept(tmp_path, "a") == "---\ntype: T\ntitle: A\n---\nbody of a\n"


def test_read_concept_missing_raises(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: T\ntitle: A\n---\nx\n"})
    with pytest.raises(ConceptNotFound):
        read_concept(tmp_path, "nope")


def test_read_concept_depth1_includes_neighbors(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: A\n---\n[b](b.md) [c](c.md)\n",
            "b.md": "---\ntype: T\ntitle: B\n---\nb\n",
            "c.md": "---\ntype: T\ntitle: C\n---\nc\n",
        },
    )
    out = read_concept(tmp_path, "a", depth=1)
    assert "(seed)" in out
    assert "# b" in out and "# c" in out


def test_read_concept_depth2_reaches_two_hops(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: A\n---\n[b](b.md)\n",
            "b.md": "---\ntype: T\ntitle: B\n---\n[c](c.md)\n",
            "c.md": "---\ntype: T\ntitle: C\n---\nc\n",
        },
    )
    out = read_concept(tmp_path, "a", depth=2)
    assert "# c" in out  # 2-hop reachable


def test_read_concept_depth1_excludes_two_hops(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: A\n---\n[b](b.md)\n",
            "b.md": "---\ntype: T\ntitle: B\n---\n[c](c.md)\n",
            "c.md": "---\ntype: T\ntitle: C\n---\nc\n",
        },
    )
    out = read_concept(tmp_path, "a", depth=1)
    assert "# c" not in out  # only direct neighbors at depth 1


def test_read_concept_budget_truncates_with_marker(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: A\n---\n[b](b.md)\n",
            "b.md": "---\ntype: T\ntitle: B\n---\n" + "x" * 400 + "\n",
        },
    )
    out = read_concept(tmp_path, "a", depth=1, token_budget=10)
    assert "(seed)" in out
    assert "omitted" in out
    assert "b" in out  # neighbor named in the truncation marker


def test_read_concept_cycle_safe(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: A\n---\n[b](b.md)\n",
            "b.md": "---\ntype: T\ntitle: B\n---\n[a](a.md)\n",
        },
    )
    out = read_concept(tmp_path, "a", depth=3)  # must terminate, not loop
    assert "(seed)" in out
    assert "# b" in out


def test_read_concept_deterministic(tmp_path):
    _bundle(
        tmp_path,
        {
            "a.md": "---\ntype: T\ntitle: A\n---\n[b](b.md) [c](c.md)\n",
            "b.md": "---\ntype: T\ntitle: B\n---\nb\n",
            "c.md": "---\ntype: T\ntitle: C\n---\nc\n",
        },
    )
    assert read_concept(tmp_path, "a", depth=1) == read_concept(tmp_path, "a", depth=1)
