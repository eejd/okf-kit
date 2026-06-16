"""Tests for okf_kit.mcp — the `okf-mcp` server: tools + okf:// resources."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from okf_kit.core.context import ConceptNotFound
from okf_kit.mcp import BundleRegistry, make_server, tool_read_concept, tool_search, tool_validate


def _bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.md").write_text("---\nokf_version: '0.1'\n---\n# Root\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("---\ntype: Table\ntitle: Alpha\ndescription: d\n---\nalpha\n", encoding="utf-8")
    (tmp_path / "tables").mkdir()
    (tmp_path / "tables" / "users.md").write_text(
        "---\ntype: Table\ntitle: Users\ndescription: Users table\n---\nbody\n", encoding="utf-8"
    )
    return tmp_path


def test_registry_resolves_and_raises(tmp_path: Path):
    root = _bundle(tmp_path)
    reg = BundleRegistry({"kb": root})
    assert reg.get("kb") == root.resolve()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_tool_search_returns_dicts(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    hits = tool_search(reg, "kb", "alpha")
    assert hits and hits[0]["cid"] == "a"


def test_tool_read_concept_returns_markdown(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    assert "Alpha" in tool_read_concept(reg, "kb", "a")


def test_tool_read_concept_missing_raises(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    with pytest.raises(ConceptNotFound):
        tool_read_concept(reg, "kb", "nope")


def test_tool_validate_returns_report_dict(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    report = tool_validate(reg, "kb")
    assert report["conformant"] is True
    assert "errors" in report and "warnings" in report and "info" in report


def test_make_server_registers_three_tools(tmp_path: Path):
    server = make_server({"kb": _bundle(tmp_path)})
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"search", "read_concept", "validate"} <= names
    for tool in tools:
        assert tool.description and len(tool.description) > 30  # agent-triggerable


def test_make_server_registers_okf_resources(tmp_path: Path):
    server = make_server({"kb": _bundle(tmp_path)})
    resources = asyncio.run(server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert "okf://kb/concepts/a.md" in uris
    assert "okf://kb/concepts/tables/users.md" in uris
