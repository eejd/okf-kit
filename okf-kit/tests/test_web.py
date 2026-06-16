"""Tests for okf_kit.web.server — the pure route() router (no sockets)."""
from __future__ import annotations

import json
from pathlib import Path

from okf_kit.web.server import route


def _bundle(tmp_path: Path) -> Path:
    (tmp_path / "index.md").write_text("---\nokf_version: '0.1'\n---\n# Root\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("---\ntype: Table\ntitle: Alpha\ndescription: d\n---\nalpha [b](b.md)\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\ntype: Metric\ntitle: Beta\ndescription: d\n---\nbeta\n", encoding="utf-8")
    return tmp_path


def _body(resp):
    return json.loads(resp.body)


def test_route_index(tmp_path: Path):
    resp = route("GET", "/api/index", _bundle(tmp_path))
    assert resp.status == 200
    data = _body(resp)
    assert {c["cid"] for c in data["concepts"]} == {"a", "b"}
    assert "Table" in data["types"]


def test_route_search(tmp_path: Path):
    resp = route("GET", "/api/search?q=alpha", _bundle(tmp_path))
    hits = _body(resp)
    assert hits and hits[0]["cid"] == "a"


def test_route_concept_and_backlinks(tmp_path: Path):
    resp = route("GET", "/api/concepts/b", _bundle(tmp_path))
    assert resp.status == 200
    concept = _body(resp)
    assert concept["cid"] == "b"
    assert concept["backlinks"] == ["a"]  # a links to b


def test_route_concept_not_found(tmp_path: Path):
    _bundle(tmp_path)
    assert route("GET", "/api/concepts/missing", tmp_path).status == 404


def test_route_concept_traversal_is_404(tmp_path: Path):
    _bundle(tmp_path)
    assert route("GET", "/api/concepts/../../etc/passwd", tmp_path).status == 404


def test_route_graph(tmp_path: Path):
    data = _body(route("GET", "/api/graph", _bundle(tmp_path)))
    ids = {e["data"].get("id") for e in data["elements"]}
    assert "a" in ids and "a->b" in ids


def test_route_static_index(tmp_path: Path):
    resp = route("GET", "/", tmp_path)
    assert resp.status == 200
    assert b"<!doctype html>" in resp.body.lower()


def test_route_static_traversal_forbidden(tmp_path: Path):
    _bundle(tmp_path)
    assert route("GET", "/../../../etc/passwd", tmp_path).status == 403


def test_route_method_not_allowed(tmp_path: Path):
    assert route("POST", "/api/index", _bundle(tmp_path)).status == 405
