"""Tests for okf_kit.mcp — the `okf-mcp` server: tools + okf:// resources."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from okf_kit.core.context import ConceptNotFound
from okf_kit.mcp import (
    BundleRegistry,
    make_server,
    tool_create_concept,
    tool_init_bundle,
    tool_read_concept,
    tool_search,
    tool_validate,
)


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


def test_make_server_registers_all_tools(tmp_path: Path):
    server = make_server({"kb": _bundle(tmp_path)})
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"search", "read_concept", "validate", "create_concept", "init_bundle"} <= names
    for tool in tools:
        assert tool.description and len(tool.description) > 30  # agent-triggerable


def test_make_server_publishes_argument_metadata_and_annotations(tmp_path: Path):
    server = make_server({"kb": _bundle(tmp_path)})
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    search_schema = tools["search"].inputSchema
    assert search_schema["properties"]["query"]["description"].startswith("Search terms")
    assert search_schema["properties"]["limit"]["minimum"] == 1
    assert search_schema["properties"]["limit"]["maximum"] == 100
    assert tools["search"].annotations.readOnlyHint is True
    assert tools["search"].annotations.openWorldHint is False

    read_schema = tools["read_concept"].inputSchema
    assert read_schema["properties"]["concept_id"]["pattern"]
    assert read_schema["properties"]["depth"]["maximum"] == 5
    assert tools["read_concept"].annotations.readOnlyHint is True

    create_schema = tools["create_concept"].inputSchema
    assert "Substantive Markdown body" in create_schema["properties"]["body"]["description"]
    assert "cid" in create_schema["required"]
    assert tools["create_concept"].annotations.readOnlyHint is False
    assert tools["create_concept"].annotations.destructiveHint is False

    init_tool = tools["init_bundle"]
    assert init_tool.annotations.destructiveHint is True
    assert init_tool.annotations.idempotentHint is True


def test_make_server_registers_okf_resources(tmp_path: Path):
    server = make_server({"kb": _bundle(tmp_path)})
    resources = asyncio.run(server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert "okf://kb/concepts/a.md" in uris
    assert "okf://kb/concepts/tables/users.md" in uris


# --- create_concept (richness floor) + init_bundle -------------------------


def test_tool_create_concept_rejects_thin_body(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    thin = "# Stub\n\nshort body\n"  # too few words, no depth section
    with pytest.raises(ValueError):
        tool_create_concept(reg, "kb", "thin", "Table", "T", "d", thin)


def test_tool_create_concept_accepts_rich_body(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    rich = "# Overview\n\n" + ("word " * 130) + "\n\n# Examples\n\n```\nokf new kb Table t\n```\n"
    res = tool_create_concept(reg, "kb", "rich", "Table", "Rich", "a rich concept", rich)
    assert res["created"] is True
    assert (tmp_path / "rich.md").is_file()


def test_tool_create_concept_rejects_traversal(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    rich = "# Overview\n\n" + ("word " * 130) + "\n\n# Examples\n\nx\n"
    with pytest.raises(ValueError):
        tool_create_concept(reg, "kb", "../escape", "Table", "T", "d", rich)


def test_tool_init_bundle(tmp_path: Path):
    reg = BundleRegistry({"kb": tmp_path / "newkb"})
    res = tool_init_bundle(reg, "kb")
    assert res["initialized"] is True
    assert (tmp_path / "newkb" / "index.md").is_file()
