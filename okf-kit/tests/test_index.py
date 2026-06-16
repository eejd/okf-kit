"""Tests for okf_kit.core.index — index.md regeneration (REQ-BM-05, REQ-PROD-05, SPEC §6)."""
from __future__ import annotations

from pathlib import Path

from okf_kit.core.index import regenerate_indexes


def _bundle(tmp_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_regenerate_indexes_type_grouped_with_subdirs(tmp_path):
    _bundle(
        tmp_path,
        {
            "tables/customers.md": "---\ntype: Table\ntitle: Customers\ndescription: Customer master data\n---\nx\n",
            "tables/orders.md": "---\ntype: Table\ntitle: Orders\ndescription: Order log\n---\nx\n",
            "playbooks/incident.md": "---\ntype: Playbook\ntitle: Incident Response\ndescription: On-call runbook\n---\nx\n",
        },
    )
    written = regenerate_indexes(tmp_path)
    assert (tmp_path / "tables" / "index.md") in written

    tables_idx = (tmp_path / "tables" / "index.md").read_text()
    assert "# Table" in tables_idx
    assert "customers" in tables_idx and "orders" in tables_idx
    assert "Customer master data" in tables_idx

    root_idx = (tmp_path / "index.md").read_text()
    assert "tables" in root_idx and "playbooks" in root_idx  # subdirectories linked


def test_regenerate_indexes_root_preserves_okf_version(tmp_path):
    _bundle(
        tmp_path,
        {
            "index.md": "---\nokf_version: '0.1'\n---\n# Old root\n",
            "a.md": "---\ntype: T\ntitle: A\ndescription: d\n---\nx\n",
        },
    )
    regenerate_indexes(tmp_path)
    root_idx = (tmp_path / "index.md").read_text()
    assert "okf_version" in root_idx and "0.1" in root_idx


def test_regenerate_indexes_returns_written_paths(tmp_path):
    _bundle(tmp_path, {"a.md": "---\ntype: T\ntitle: A\ndescription: d\n---\nx\n"})
    written = regenerate_indexes(tmp_path)
    assert (tmp_path / "index.md") in written


def test_regenerate_indexes_empty_bundle_writes_none(tmp_path):
    assert regenerate_indexes(tmp_path) == []
