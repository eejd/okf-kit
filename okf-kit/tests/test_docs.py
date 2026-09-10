"""Docs tests: the `docs/` folder was folded into the `wiki/` bundle, so this now
guards the wiki as the documentation home.

- The migrated reference concepts exist in the wiki.
- The canonical tool descriptions in `wiki/reference/tools.md` are synced with the
  strings in `okf_kit/mcp.py` (design §11 — tools documented in synced places).
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

from okf_kit import __version__
from okf_kit.mcp import (
    _CREATE_DESC,
    _GRAPH_DESC,
    _INIT_DESC,
    _LIST_BUNDLES_DESC,
    _READ_DESC,
    _SEARCH_DESC,
    _SYNC_STATUS_DESC,
    _VALIDATE_DESC,
    BundleRegistry,
    GitBackend,
    tool_sync_status,
)

WIKI = Path(__file__).resolve().parent.parent.parent / "wiki"
TOOLS_REFERENCE = WIKI / "reference" / "tools.md"


def test_reference_concepts_exist():
    """The former docs/ content now lives in these wiki concepts."""
    for rel in (
        "reference/tools.md",
        "interfaces/okf-uri-scheme.md",
        "guides/authoring.md",
        "project/backlog.md",
    ):
        assert (WIKI / rel).is_file(), f"missing wiki reference concept: {rel}"


def test_package_runtime_version_matches_project_metadata():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert __version__ == metadata["project"]["version"] == "0.3.0"


def test_readme_documents_write_guard_and_search_compatibility():
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    assert "--expected-write-branch" in readme
    assert "v0.3 — governed OKF access and authoring" in readme
    assert "Git-backed preview authoring" in readme
    assert "explicit preview refspec" in readme
    assert "response_version=legacy" in readme
    assert '"schema_version":"1"' in readme
    assert "searches with no results" in readme
    assert "`--help` exits `0`" in readme


def test_wiki_documents_search_shapes_and_cli_exit_semantics():
    response_docs = [
        TOOLS_REFERENCE,
        WIKI / "interfaces" / "okf-cli.md",
        WIKI / "interfaces" / "okf-mcp.md",
        WIKI / "core" / "search.md",
    ]
    for path in response_docs:
        text = path.read_text(encoding="utf-8")
        assert '"schema_version":"1"' in text, path
        assert "results" in text and "total" in text and "next_cursor" in text, path
        assert "cid" in text and "snippet" in text and "score" in text, path
        assert "legacy" in text.lower() and "cursor" in text.lower(), path

    exit_docs = [TOOLS_REFERENCE, WIKI / "interfaces" / "okf-cli.md"]
    for path in exit_docs:
        text = path.read_text(encoding="utf-8")
        assert "no search" in text, path
        assert "warnings/info only" in text, path
        assert "`--help` exits `0`" in text, path
        assert "invalid cursor" in text, path


def test_hive_conformance_fixture_contract_is_documented():
    text = (WIKI / "core" / "validate.md").read_text(encoding="utf-8")
    assert "canonically owned by\nknowledge-hive" in text
    assert "byte-identical" in text
    assert "faf157d80fadb4269807e020ae96c42aba37c6b8cbd959eb0b99c6bc9d3e28cc" in text
    assert "both repositories must\nassert and execute that exact digest" in text


def _documented_sync_status_keys(text: str, group: str) -> set[str]:
    match = re.search(rf"<!-- sync-status-{group}-keys: ([a-z_,]+) -->", text)
    assert match, f"missing sync_status {group} key contract"
    return set(match.group(1).split(","))


def test_sync_status_documented_keys_match_runtime(tmp_path: Path):
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    tracked_root = tmp_path / "tracked"
    tracked_root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(tracked_root)], check=True, env=git_env)
    (tracked_root / "concept.md").write_text("---\ntype: Note\n---\nbody\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tracked_root), "add", "concept.md"], check=True, env=git_env)
    subprocess.run(
        [
            "git",
            "-C",
            str(tracked_root),
            "-c",
            "user.name=docs-test",
            "-c",
            "user.email=docs@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        check=True,
        env=git_env,
    )
    loose_root = tmp_path / "loose"
    loose_root.mkdir()
    reg = BundleRegistry({"tracked": tracked_root, "loose": loose_root})
    backend = GitBackend(reg)

    untracked = tool_sync_status(reg, backend, "loose")
    tracked = tool_sync_status(reg, backend, "tracked")
    docs = TOOLS_REFERENCE.read_text(encoding="utf-8")
    base_keys = _documented_sync_status_keys(docs, "base")
    git_keys = _documented_sync_status_keys(docs, "git")

    assert set(untracked) == base_keys
    assert set(tracked) == base_keys | git_keys
    assert tracked["sha"] == tracked["served_sha"]

    subprocess.run(
        ["git", "-C", str(tracked_root), "checkout", "-q", "--detach"],
        check=True,
        env=git_env,
    )
    detached = tool_sync_status(reg, GitBackend(reg), "tracked")
    assert detached["branch"] is None
    assert detached["detached"] is True


def _extract_description(md: str, tool: str) -> str:
    pattern = rf"## {re.escape(tool)}.*?<!-- desc:start -->\n(.*?)\n<!-- desc:end -->"
    match = re.search(pattern, md, re.DOTALL)
    assert match, f"no canonical description block for tool '{tool}' in {TOOLS_REFERENCE}"
    return match.group(1).strip()


def test_tool_reference_synced_with_mcp_descriptions():
    md = TOOLS_REFERENCE.read_text(encoding="utf-8")
    assert _extract_description(md, "search") == _SEARCH_DESC
    assert _extract_description(md, "read_concept") == _READ_DESC
    assert _extract_description(md, "validate") == _VALIDATE_DESC
    assert _extract_description(md, "create_concept") == _CREATE_DESC
    assert _extract_description(md, "graph_links") == _GRAPH_DESC
    assert _extract_description(md, "init_bundle") == _INIT_DESC
    assert _extract_description(md, "list_bundles") == _LIST_BUNDLES_DESC
    assert _extract_description(md, "sync_status") == _SYNC_STATUS_DESC


def test_agent_installer_docs_are_skill_only():
    docs = [
        Path(__file__).resolve().parent.parent.parent / "README.md",
        WIKI / "interfaces" / "okf-cli.md",
        WIKI / "guides" / "authoring.md",
        TOOLS_REFERENCE,
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        compact = " ".join(text.split())
        assert "okf agent install" in text, path
        assert "okf-search" in text, path
        assert "okf-author" in text, path
        assert "does not install subagents" in compact or "no subagents" in compact, path


def test_code_index_docs_are_syntax_grounded_and_polyglot():
    docs = [
        Path(__file__).resolve().parent.parent.parent / "README.md",
        WIKI / "interfaces" / "okf-cli.md",
        WIKI / "guides" / "authoring.md",
        TOOLS_REFERENCE,
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        compact = " ".join(text.split()).lower()
        assert "okf-kit[treesitter]" in text, path
        assert "okf code index" in text, path
        assert "--profile compact" in compact, path
        assert "--include-tests" in compact, path
        assert "--include" in compact, path
        assert "--exclude" in compact, path
        assert "--repo" in compact, path
        assert "codesummary" in compact, path
        assert "reverse-dependent" in compact or "reverse dependent" in compact, path
        assert "python" in compact, path
        assert "typescript" in compact, path
        assert "rust" in compact, path
        assert "go" in compact, path
        assert "csharp" in compact or "c#" in compact, path
        assert "php" in compact, path
        assert "semantic proof" in compact or "semantic impact analysis" in compact, path
