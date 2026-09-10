"""Docs tests: the `docs/` folder was folded into the `wiki/` bundle, so this now
guards the wiki as the documentation home.

- The migrated reference concepts exist in the wiki.
- The canonical tool descriptions in `wiki/reference/tools.md` are synced with the
  strings in `okf_kit/mcp.py` (design §11 — tools documented in synced places).
"""
from __future__ import annotations

import re
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
