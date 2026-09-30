"""Integration tests for hub->serve convergence wired into okf_kit.mcp.make_server:
revalidate-on-use, the /okf/refresh route, live resources, and the
sync_status convergence fields. Complements test_sync.py (the pure
GitWriter.converge / SyncCoordinator unit tests) and test_gitio.py (the
--git-commit write path).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from okf_kit.mcp import make_server, tool_sync_status
from starlette.testclient import TestClient


def _run(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=env
    )
    return proc.stdout.strip()


def _hub_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A bare hub plus a working clone containing one bundle ``kb``."""
    hub = tmp_path / "hub.git"
    hub.mkdir()
    _run(hub, "init", "--bare", "-b", "main")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", str(hub), str(clone)], capture_output=True, text=True, check=True
    )
    (clone / "index.md").write_text("---\nokf_version: '0.2'\n---\n# kb\n", encoding="utf-8")
    (clone / "a.md").write_text(
        "---\ntype: Table\ntitle: Alpha\ndescription: d\n---\nalpha\n", encoding="utf-8"
    )
    _run(clone, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _run(clone, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "seed")
    _run(clone, "push", "origin", "main")
    return hub, clone


def _advance_hub(hub: Path, tmp_path: Path, name: str, *, tag: str) -> str:
    other = tmp_path / f"other-{tag}"
    subprocess.run(
        ["git", "clone", str(hub), str(other)], capture_output=True, text=True, check=True
    )
    (other / name).write_text(
        f"---\ntype: Table\ntitle: {name}\ndescription: d\n---\nbody\n", encoding="utf-8"
    )
    _run(other, "add", ".")
    _run(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", tag)
    _run(other, "push", "origin", "main")
    return _run(other, "rev-parse", "HEAD")


# -- startup sync -------------------------------------------------------


def test_make_server_syncs_once_at_startup(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    new_sha = _advance_hub(hub, tmp_path, "b.md", tag="ahead-of-clone")
    server = make_server({"kb": clone}, sync_branch="main", refresh_route=False)
    assert _run(clone, "rev-parse", "HEAD") == new_sha
    resources = asyncio.run(server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert "okf://kb/concepts/b.md" in uris


def test_make_server_startup_sync_tolerates_no_remote(tmp_path: Path):
    """A bundle with no git remote (or no git at all) must not fail server
    construction — sync is best-effort background convergence, not a
    precondition for serving."""
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "index.md").write_text("---\nokf_version: '0.2'\n---\n# kb\n", encoding="utf-8")
    server = make_server({"kb": loose}, refresh_route=False)
    assert server is not None


# -- revalidate-on-use ----------------------------------------------------


def test_tool_call_self_heals_after_stale_interval(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    server = make_server(
        {"kb": clone}, sync_branch="main", sync_revalidate=0.01, refresh_route=False
    )
    before = _run(clone, "rev-parse", "HEAD")
    new_sha = _advance_hub(hub, tmp_path, "b.md", tag="ff")
    assert _run(clone, "rev-parse", "HEAD") == before  # not yet synced
    time.sleep(0.02)
    result = asyncio.run(server.call_tool("list_bundles", {}))
    assert result is not None
    assert _run(clone, "rev-parse", "HEAD") == new_sha


def test_tool_call_within_interval_does_not_sync(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    server = make_server(
        {"kb": clone}, sync_branch="main", sync_revalidate=100.0, refresh_route=False
    )
    before = _run(clone, "rev-parse", "HEAD")
    _advance_hub(hub, tmp_path, "b.md", tag="ff")
    asyncio.run(server.call_tool("list_bundles", {}))
    assert _run(clone, "rev-parse", "HEAD") == before


# -- sync_status convergence fields --------------------------------------


def test_sync_status_reports_convergence_fields(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    _advance_hub(hub, tmp_path, "b.md", tag="ff")
    server = make_server({"kb": clone}, sync_branch="main", refresh_route=False)
    status = asyncio.run(server.call_tool("sync_status", {"bundle": "kb"}))
    payload = status[1] if isinstance(status, tuple) else status
    # call_tool returns (content_blocks, structured_result) for a dict-returning tool.
    data = payload if isinstance(payload, dict) else payload.get("result", payload)
    assert data.get("sync_action") == "fast-forward"
    assert data.get("hub_sha") == _run(clone, "rev-parse", "HEAD")
    assert data.get("last_sync_at") is not None
    assert data.get("last_sync_error") is None


def test_tool_sync_status_no_coordinator_omits_sync_fields(tmp_path: Path):
    from okf_kit.mcp import BundleRegistry, GitBackend

    reg = BundleRegistry({"kb": tmp_path})
    (tmp_path / "index.md").write_text("---\nokf_version: '0.2'\n---\n# kb\n", encoding="utf-8")
    git = GitBackend(reg)
    result = tool_sync_status(reg, git, "kb")
    assert "sync_action" not in result


# -- /okf/refresh route ---------------------------------------------------


def test_refresh_route_triggers_sync(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    server = make_server({"kb": clone}, sync_branch="main", sync_revalidate=0, refresh_route=True)
    new_sha = _advance_hub(hub, tmp_path, "b.md", tag="ff")
    before = _run(clone, "rev-parse", "HEAD")
    assert before != new_sha
    app = server.streamable_http_app()
    with TestClient(app) as client:
        response = client.post("/okf/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["synced"][0]["bundle"] == "kb"
    assert body["synced"][0]["sync_action"] == "fast-forward"
    assert _run(clone, "rev-parse", "HEAD") == new_sha


def test_refresh_route_disabled_returns_404(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    server = make_server({"kb": clone}, sync_branch="main", refresh_route=False)
    app = server.streamable_http_app()
    with TestClient(app) as client:
        response = client.post("/okf/refresh")
    assert response.status_code == 404


def test_refresh_route_noop_without_git_remote(tmp_path: Path):
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "index.md").write_text("---\nokf_version: '0.2'\n---\n# kb\n", encoding="utf-8")
    server = make_server({"kb": loose}, refresh_route=True)
    app = server.streamable_http_app()
    with TestClient(app) as client:
        response = client.post("/okf/refresh")
    assert response.status_code == 200
    assert response.json() == {"synced": []}


# -- live resources ---------------------------------------------------------


def test_new_concept_appears_in_resources_without_restart(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    server = make_server({"kb": clone}, sync_branch="main", sync_revalidate=0, refresh_route=True)
    baseline = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert "okf://kb/concepts/c.md" not in baseline
    _advance_hub(hub, tmp_path, "c.md", tag="new-concept")
    app = server.streamable_http_app()
    with TestClient(app) as client:
        client.post("/okf/refresh")
    after = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert "okf://kb/concepts/c.md" in after


def test_read_resource_reads_live_content(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    server = make_server({"kb": clone}, sync_branch="main", refresh_route=False)
    contents = asyncio.run(server.read_resource("okf://kb/concepts/a.md"))
    text = list(contents)[0].content
    assert "alpha" in text
    (clone / "a.md").write_text(
        "---\ntype: Table\ntitle: Alpha\ndescription: d\n---\nchanged\n", encoding="utf-8"
    )
    contents2 = asyncio.run(server.read_resource("okf://kb/concepts/a.md"))
    assert "changed" in list(contents2)[0].content


def test_read_resource_unknown_concept_raises(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    server = make_server({"kb": clone}, sync_branch="main", refresh_route=False)
    with pytest.raises(ValueError):
        asyncio.run(server.read_resource("okf://kb/concepts/does-not-exist.md"))
