"""Tests for okf_kit.core.templates — init_bundle, create_concept, type templates (REQ-ED-05, REQ-PROD-08)."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_kit.core.templates import TEMPLATE_TYPES, create_concept, init_bundle


def test_init_bundle_creates_root_index(tmp_path: Path):
    root = tmp_path / "mykb"
    init_bundle(root)
    idx = (root / "index.md").read_text()
    assert "okf_version" in idx and "0.1" in idx


def test_create_concept_writes_template(tmp_path: Path):
    root = tmp_path / "kb"
    init_bundle(root)
    p = create_concept(root, "tables/users", "Table", title="Users", description="User accounts.")
    text = p.read_text()
    assert "type: Table" in text
    assert "title: Users" in text
    assert "description: User accounts." in text
    assert "# Schema" in text


def test_create_concept_generic_fallback(tmp_path: Path):
    root = tmp_path / "kb"
    init_bundle(root)
    p = create_concept(root, "notes/thing", "Whatever")
    text = p.read_text()
    assert "type: Whatever" in text
    assert "# Overview" in text  # generic body scaffold


def test_create_concept_rejects_invalid_cid(tmp_path: Path):
    root = tmp_path / "kb"
    init_bundle(root)
    with pytest.raises(ValueError):
        create_concept(root, "../escape", "Table")


def test_create_concept_rejects_existing(tmp_path: Path):
    root = tmp_path / "kb"
    init_bundle(root)
    create_concept(root, "a", "Table")
    with pytest.raises(FileExistsError):
        create_concept(root, "a", "Table")


def test_template_types_include_common():
    assert "Table" in TEMPLATE_TYPES
    assert "Metric" in TEMPLATE_TYPES
    assert "Playbook" in TEMPLATE_TYPES


def test_create_concept_rejects_symlink_dir_escape(tmp_path: Path):
    root = tmp_path / "kb"
    init_bundle(root)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    escape = root / "escape"
    try:
        escape.symlink_to(outside_dir)
    except OSError:
        pytest.skip("symlinks not supported")
    try:
        with pytest.raises(ValueError):  # parent resolves outside the bundle root
            create_concept(root, "escape/x", "Table")
    finally:
        if escape.is_symlink() or escape.exists():
            escape.unlink()
