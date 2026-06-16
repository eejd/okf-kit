"""Docs tests: the 4 doc files exist, and docs/tools.md descriptions are synced
with the canonical strings in okf_kit/mcp.py (design §11 — tools documented in
synced places)."""
from __future__ import annotations

import re
from pathlib import Path

from okf_kit.mcp import _READ_DESC, _SEARCH_DESC, _VALIDATE_DESC

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"


def test_doc_files_exist():
    for name in ("tools.md", "progressive-context.md", "okf-uri-scheme.md", "authoring.md"):
        assert (DOCS / name).is_file(), f"missing doc: {name}"


def _extract_description(md: str, tool: str) -> str:
    pattern = rf"## {re.escape(tool)}.*?<!-- desc:start -->\n(.*?)\n<!-- desc:end -->"
    match = re.search(pattern, md, re.DOTALL)
    assert match, f"no canonical description block for tool '{tool}' in docs/tools.md"
    return match.group(1).strip()


def test_tools_md_synced_with_mcp_descriptions():
    md = (DOCS / "tools.md").read_text(encoding="utf-8")
    assert _extract_description(md, "search") == _SEARCH_DESC
    assert _extract_description(md, "read_concept") == _READ_DESC
    assert _extract_description(md, "validate") == _VALIDATE_DESC
