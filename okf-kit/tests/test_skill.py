"""Goal-based test: the okf-author skill exists and is well-formed (agentskills.io)."""
from __future__ import annotations

from pathlib import Path

from okf_kit.core.parse import split_frontmatter

SKILL = Path(__file__).resolve().parent.parent / "skills" / "okf-author" / "SKILL.md"


def test_skill_md_exists():
    assert SKILL.is_file(), f"missing skill file: {SKILL}"


def test_skill_md_frontmatter():
    result = split_frontmatter(SKILL.read_text(encoding="utf-8"))
    assert result.present
    assert result.error is None
    assert result.data["name"] == "okf-author"
    desc = result.data.get("description", "")
    assert isinstance(desc, str) and len(desc) > 40
    # body documents the author loop and points at the okf CLI
    body = result.body
    assert "okf new" in body
    assert "okf validate" in body
    assert "okf index regen" in body
