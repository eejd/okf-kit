"""Tests for okf_kit.core.model + okf_kit.core.parse.

Written to the SPEC §9 / REQ-CONS-01..04 contract before implementation.
"""
from __future__ import annotations

from pathlib import Path

from okf_kit.core.model import Concept
from okf_kit.core.parse import (
    FrontmatterResult,
    parse_concept,
    serialize_concept,
    split_frontmatter,
)


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# --- split_frontmatter -----------------------------------------------------


def test_split_standard_frontmatter():
    text = "---\ntype: Table\ntitle: Users\n---\n\n# Schema\n\nbody text\n"
    res = split_frontmatter(text)
    assert res.present
    assert res.error is None
    assert res.data == {"type": "Table", "title": "Users"}
    assert "# Schema" in res.body and "body text" in res.body


def test_split_preserves_unknown_and_nested_keys():
    text = "---\ntype: Table\nowner: team-x\ncustom:\n  - a\n  - b\n---\nbody\n"
    res = split_frontmatter(text)
    assert res.data["owner"] == "team-x"
    assert res.data["custom"] == ["a", "b"]


def test_split_no_frontmatter_is_graceful():
    text = "# Just a title\n\nsome body\n"
    res = split_frontmatter(text)
    assert not res.present
    assert res.error is None
    assert res.data == {}
    assert res.body == text


def test_split_empty_frontmatter_block():
    text = "---\n---\nbody after empty fm\n"
    res = split_frontmatter(text)
    assert res.present
    assert res.error is None
    assert res.data == {}
    assert "body after empty fm" in res.body


def test_split_non_mapping_is_error():
    text = "---\n- a\n- b\n---\nbody\n"
    res = split_frontmatter(text)
    assert res.present
    assert res.error is not None
    assert res.data == {}


def test_split_unparseable_yaml_is_error():
    text = "---\ntype: Table\n  bad: : : indent\n---\nbody\n"
    res = split_frontmatter(text)
    assert res.present
    assert res.error is not None
    assert res.data == {}


def test_split_unclosed_frontmatter_graceful():
    text = "---\ntype: Table\nbut no closing delimiter\n"
    res = split_frontmatter(text)
    assert not res.present
    assert res.error is None
    assert res.data == {}
    assert "no closing delimiter" in res.body


def test_split_leading_whitespace_before_delimiter_not_frontmatter():
    text = " ---\ntype: Table\n---\nbody\n"
    res = split_frontmatter(text)
    assert not res.present
    assert res.data == {}


def test_split_bom_before_delimiter_not_frontmatter():
    text = "﻿---\ntype: Table\n---\nbody\n"
    res = split_frontmatter(text)
    assert not res.present


def test_split_empty_text():
    res = split_frontmatter("")
    assert not res.present
    assert res.data == {}
    assert res.body == ""


# --- parse_concept ---------------------------------------------------------


def test_parse_concept_basic(tmp_path):
    _write(
        tmp_path,
        "tables/users.md",
        "---\ntype: Table\ntitle: Users\ndescription: User accounts.\n---\n\n# Schema\n\ncols\n",
    )
    c = parse_concept(tmp_path / "tables/users.md", tmp_path)
    assert isinstance(c, Concept)
    assert c.cid == "tables/users"
    assert c.root == tmp_path
    assert c.reserved is None
    assert c.frontmatter["type"] == "Table"
    assert c.frontmatter["title"] == "Users"
    assert "# Schema" in c.body
    assert c.frontmatter_error is None


def test_parse_concept_root_level_cid(tmp_path):
    _write(tmp_path, "glossary.md", "---\ntype: Term\n---\nbody\n")
    c = parse_concept(tmp_path / "glossary.md", tmp_path)
    assert c.cid == "glossary"


def test_parse_concept_index_reserved(tmp_path):
    _write(tmp_path, "tables/index.md", "# Tables\n\n- [users](users.md)\n")
    c = parse_concept(tmp_path / "tables/index.md", tmp_path)
    assert c.reserved == "index"


def test_parse_concept_log_reserved(tmp_path):
    _write(tmp_path, "log.md", "# 2026-01-01\n\n**Creation** init\n")
    c = parse_concept(tmp_path / "log.md", tmp_path)
    assert c.reserved == "log"


def test_parse_concept_no_frontmatter_degraded(tmp_path):
    _write(tmp_path, "orphan.md", "no frontmatter here\n")
    c = parse_concept(tmp_path / "orphan.md", tmp_path)
    assert c.frontmatter == {}
    assert c.body == "no frontmatter here\n"
    # graceful at parse level; the *validator* turns this into an error
    assert c.frontmatter_error is None


def test_parse_concept_non_mapping_records_error(tmp_path):
    _write(tmp_path, "bad.md", "---\n- a\n- b\n---\nbody\n")
    c = parse_concept(tmp_path / "bad.md", tmp_path)
    assert c.frontmatter_error is not None
    assert c.frontmatter == {}


# --- serialize round-trip --------------------------------------------------


def test_serialize_roundtrip_preserves_frontmatter_and_body(tmp_path):
    _write(
        tmp_path,
        "tables/users.md",
        "---\ntype: Table\ntitle: Users\n---\n\n# Schema\n\nbody\n",
    )
    c = parse_concept(tmp_path / "tables/users.md", tmp_path)
    text = serialize_concept(c)
    res = split_frontmatter(text)
    assert isinstance(res, FrontmatterResult)
    assert res.data["type"] == "Table"
    assert res.data["title"] == "Users"
    assert "# Schema" in res.body


def test_frontmatter_present_flag(tmp_path):
    _write(tmp_path, "with.md", "---\ntype: T\n---\nbody\n")
    _write(tmp_path, "empty_block.md", "---\n---\nbody\n")
    _write(tmp_path, "without.md", "no block\n")
    assert parse_concept(tmp_path / "with.md", tmp_path).frontmatter_present is True
    assert parse_concept(tmp_path / "empty_block.md", tmp_path).frontmatter_present is True
    assert parse_concept(tmp_path / "without.md", tmp_path).frontmatter_present is False


def test_parse_concept_size_cap(tmp_path, monkeypatch):
    from okf_kit.core import parse as parse_mod

    monkeypatch.setattr(parse_mod, "_MAX_CONCEPT_BYTES", 8)
    _write(tmp_path, "big.md", "---\ntype: T\n---\n" + "x" * 100 + "\n")
    concept = parse_concept(tmp_path / "big.md", tmp_path)
    assert concept.frontmatter_error is not None
    assert "too large" in concept.frontmatter_error
