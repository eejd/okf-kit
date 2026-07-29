"""Tests for okf_kit.mcp — the `okf-mcp` server: tools + okf:// resources."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from okf_kit.core.context import ConceptNotFound
from okf_kit.core.parse import parse_concept
from okf_kit.mcp import (
    BundleRegistry,
    DuplicateBundleNameError,
    _parse_bundle_arg,
    make_server,
    tool_create_concept,
    tool_init_bundle,
    tool_list_bundles,
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


# --- Tool-call logging (stderr, never stdout — see _log_tool_call docstring) ---


def _last_log_record(capsys: pytest.CaptureFixture) -> dict:
    captured = capsys.readouterr()
    assert captured.out == "", "tool-call logs must never write to stdout (the MCP wire)"
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert lines, "expected at least one log line on stderr"
    return json.loads(lines[-1])


def test_tool_search_logs_to_stderr_not_stdout(tmp_path: Path, capsys: pytest.CaptureFixture):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    tool_search(reg, "kb", "alpha")
    record = _last_log_record(capsys)
    assert record["tool"] == "search"
    assert record["ok"] is True
    assert record["bundle"] == "kb"
    assert record["query"] == "alpha"
    assert record["n_results"] == 1
    assert record["top_score"] > 0
    assert record["latency_ms"] >= 0
    assert "ts" in record


def test_tool_search_no_hits_logs_zero_results_and_no_top_score(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    tool_search(reg, "kb", "zzzznomatch")
    record = _last_log_record(capsys)
    assert record["n_results"] == 0
    assert "top_score" not in record  # None fields are dropped, not logged as null


def test_tool_read_concept_logs_even_on_not_found(tmp_path: Path, capsys: pytest.CaptureFixture):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    with pytest.raises(ConceptNotFound):
        tool_read_concept(reg, "kb", "nope")
    record = _last_log_record(capsys)
    assert record["tool"] == "read_concept"
    assert record["ok"] is False
    assert record["concept_id"] == "nope"


def test_tool_validate_logs_finding_counts(tmp_path: Path, capsys: pytest.CaptureFixture):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    tool_validate(reg, "kb")
    record = _last_log_record(capsys)
    assert record["tool"] == "validate"
    assert record["n_errors"] == 0
    assert isinstance(record["n_warnings"], int)
    assert isinstance(record["n_info"], int)


def test_tool_list_bundles_logs_count(tmp_path: Path, capsys: pytest.CaptureFixture):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    tool_list_bundles(reg)
    record = _last_log_record(capsys)
    assert record["tool"] == "list_bundles"
    assert record["n_bundles"] == 1


def test_make_server_registers_all_tools(tmp_path: Path):
    server = make_server({"kb": _bundle(tmp_path)})
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {
        "search", "read_concept", "validate", "create_concept", "init_bundle", "list_bundles",
    } <= names
    for tool in tools:
        assert tool.description and len(tool.description) > 30  # agent-triggerable


def test_registry_rejects_duplicate_names_from_list_form(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    with pytest.raises(DuplicateBundleNameError):
        BundleRegistry([("kb", a), ("kb", b)])


def test_registry_accepts_dict_form_unchanged(tmp_path: Path):
    root = _bundle(tmp_path)
    reg = BundleRegistry({"kb": root})
    assert reg.names() == ["kb"]


def test_tool_list_bundles_reports_registered_names(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    listed = tool_list_bundles(reg)
    assert listed == [{"bundle": "kb", "path": str(reg.get("kb"))}]


def test_parse_bundle_arg_bare_path_uses_basename():
    name, path = _parse_bundle_arg("/some/dir/mybundle")
    assert name == "mybundle"
    assert path == "/some/dir/mybundle"


def test_parse_bundle_arg_name_equals_path():
    name, path = _parse_bundle_arg("hive-dev=/bundle")
    assert name == "hive-dev"
    assert path == "/bundle"


def test_parse_bundle_arg_rejects_empty_name_or_path():
    with pytest.raises(ValueError):
        _parse_bundle_arg("=/bundle")
    with pytest.raises(ValueError):
        _parse_bundle_arg("name=")


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


def test_tool_create_concept_persists_recommended_and_extra_frontmatter(tmp_path: Path):
    reg = BundleRegistry({"kb": _bundle(tmp_path)})
    rich = "# Overview\n\n" + ("word " * 130) + "\n"
    res = tool_create_concept(
        reg, "kb", "tables/orders", "Table", "Orders", "orders table", rich,
        resource="bigquery://proj.ds.tables.orders",
        timestamp="2026-06-17T14:30:00Z",
        extra={"owner": "data-eng", "pii": True},
    )
    assert res["created"] is True
    # Round-trip through the parser: every recommended + extra field is preserved.
    fm = parse_concept(tmp_path / "tables" / "orders.md", tmp_path).frontmatter
    assert fm["type"] == "Table"
    assert fm["resource"] == "bigquery://proj.ds.tables.orders"
    assert fm["timestamp"] == "2026-06-17T14:30:00Z"  # quoted on disk, string on parse
    assert fm["owner"] == "data-eng"
    assert fm["pii"] is True


def test_tool_init_bundle(tmp_path: Path):
    reg = BundleRegistry({"kb": tmp_path / "newkb"})
    res = tool_init_bundle(reg, "kb")
    assert res["initialized"] is True
    assert (tmp_path / "newkb" / "index.md").is_file()


# --- HTTP transport wiring (WS1: hive fork addition) -------------------------


def test_make_server_accepts_host_and_port_kwargs(tmp_path: Path):
    """make_server() host/port kwargs propagate to the FastMCP Settings."""
    server = make_server({"kb": _bundle(tmp_path)}, host="127.0.0.1", port=4020)
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 4020


def test_make_server_default_host_is_loopback(tmp_path: Path):
    """Default host must be loopback — never 0.0.0.0 (security gate)."""
    server = make_server({"kb": _bundle(tmp_path)})
    assert server.settings.host == "127.0.0.1", (
        f"Default host {server.settings.host!r} is not loopback — "
        "this would expose the KB off-host without Traefik."
    )


def test_make_server_streamable_http_path_is_mcp(tmp_path: Path):
    """Streamable-HTTP path must be /mcp to match *.mcp.home.zt/mcp convention."""
    server = make_server({"kb": _bundle(tmp_path)})
    assert server.settings.streamable_http_path == "/mcp"


def test_main_transport_flag_defaults_to_stdio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--transport defaults to 'stdio'; run() receives 'stdio'."""
    from okf_kit import mcp as mcp_mod

    calls: list[str] = []

    class _FakeServer:
        def run(self, transport: str = "stdio") -> None:
            calls.append(transport)

    monkeypatch.setattr(mcp_mod, "make_server", lambda bundles, **kw: _FakeServer())
    mcp_mod.main([str(tmp_path)])
    assert calls == ["stdio"]


def test_main_transport_http_alias_maps_to_streamable_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """--transport http is an alias for streamable-http."""
    from okf_kit import mcp as mcp_mod

    calls: list[str] = []

    class _FakeServer:
        def run(self, transport: str = "stdio") -> None:
            calls.append(transport)

    monkeypatch.setattr(mcp_mod, "make_server", lambda bundles, **kw: _FakeServer())
    mcp_mod.main([str(tmp_path), "--transport", "http"])
    assert calls == ["streamable-http"]


def test_main_transport_streamable_http_direct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--transport streamable-http passes through unchanged."""
    from okf_kit import mcp as mcp_mod

    calls: list[str] = []
    kwargs_seen: list[dict] = []

    class _FakeServer:
        def run(self, transport: str = "stdio") -> None:
            calls.append(transport)

    def _fake_make_server(bundles: dict, **kw: object) -> _FakeServer:
        kwargs_seen.append(dict(kw))
        return _FakeServer()

    monkeypatch.setattr(mcp_mod, "make_server", _fake_make_server)
    mcp_mod.main([str(tmp_path), "--transport", "streamable-http", "--host", "127.0.0.1", "--port", "4021"])
    assert calls == ["streamable-http"]
    assert kwargs_seen[0]["host"] == "127.0.0.1"
    assert kwargs_seen[0]["port"] == 4021


def test_main_name_equals_path_registers_under_explicit_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """End-to-end: a NAME=PATH CLI argument reaches make_server as a bundles
    list that builds a real BundleRegistry under the explicit name — not just
    _parse_bundle_arg in isolation. The FakeServer stands in only for the
    FastMCP transport (.run()), which this test does not exercise; the
    bundles value itself is real and passed straight through main()."""
    from okf_kit import mcp as mcp_mod

    mount_point = tmp_path / "mount-point-name-would-be-wrong"
    mount_point.mkdir()
    root = _bundle(mount_point)
    registries_seen: list[mcp_mod.BundleRegistry] = []

    class _FakeServer:
        def run(self, transport: str = "stdio") -> None:
            pass

    def _spy_make_server(bundles: object, **kw: object) -> object:
        registries_seen.append(mcp_mod.BundleRegistry(bundles))  # type: ignore[arg-type]
        return _FakeServer()

    monkeypatch.setattr(mcp_mod, "make_server", _spy_make_server)
    mcp_mod.main([f"hive-dev={root}"])
    assert registries_seen[0].names() == ["hive-dev"]
    assert registries_seen[0].get("hive-dev") == root.resolve()
