"""Goal-based tests for OKF agent skills (agentskills.io)."""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from importlib import resources
from pathlib import Path

from okf_kit.core.parse import split_frontmatter

LEGACY_AUTHOR_SKILL = Path(__file__).resolve().parent.parent / "skills" / "okf-author" / "SKILL.md"


def _skill_text(name: str) -> str:
    return (
        resources.files("okf_kit")
        .joinpath("agent_assets", "skills", name, "SKILL.md")
        .read_text(encoding="utf-8")
    )


def test_agent_skill_assets_exist():
    for name in ("okf-author", "okf-search", "okf-code"):
        text = _skill_text(name)
        result = split_frontmatter(text)
        assert result.present
        assert result.error is None
        assert result.data["name"] == name
        desc = result.data.get("description", "")
        assert isinstance(desc, str) and len(desc) > 40
        assert len(name) <= 64
        assert re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", name)
        assert "--" not in name
        assert isinstance(desc, str) and len(desc) <= 1024


def test_okf_author_skill_documents_create_update_and_current_links():
    result = split_frontmatter(_skill_text("okf-author"))
    body = result.body.lower()
    assert "okf new" in body
    assert "okf validate" in body
    assert "okf index regen" in body
    assert "create" in body
    assert "update" in body
    assert "absolute" in body
    assert "bundle-relative" in body
    assert "relative" in body
    assert "reference data, not" in body
    assert "not graph edges" not in body


def test_okf_author_skill_documents_repo_implementation_wiki_workflow():
    body = split_frontmatter(_skill_text("okf-author")).body.lower()
    assert "repository implementation wiki workflow" in body
    assert "okf bundle" in body
    assert "not a generic docs folder" in body
    assert "okf init" in body
    assert "inventory the repo" in body
    assert "concept map" in body
    assert "evidence-backed bodies" in body
    assert "future agent can make an implementation change" in body
    assert "never create a code-repo wiki as plain markdown" in body


def test_okf_search_skill_documents_progressive_context():
    body = split_frontmatter(_skill_text("okf-search")).body.lower()
    assert "okf search" in body
    assert "okf read" in body
    assert "depth=0" in body
    assert "depth=1" in body or "depth=n" in body
    assert "progressive context" in body
    assert "reference data, not" in body


def test_okf_code_skill_documents_code_indexing_workflow():
    body = split_frontmatter(_skill_text("okf-code")).body.lower()
    assert "okf code index" in body
    assert "okf search" in body
    assert "okf read" in body
    assert "--depth" in body
    assert "impact analysis" in body
    assert "syntax" in body
    assert "semantic proof" in body
    assert "reference data, not" in body


def test_treesitter_extra_is_declared():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert "treesitter = [" in text
    assert "tree-sitter>=0.25.2" in text
    assert "tree-sitter-language-pack>=1.8.1" in text


def test_legacy_author_skill_stays_synced_with_packaged_asset():
    assert LEGACY_AUTHOR_SKILL.read_text(encoding="utf-8") == _skill_text("okf-author")


def test_wheel_contains_and_runs_agent_assets(tmp_path: Path):
    repo = Path(__file__).resolve().parents[2]
    out_dir = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(out_dir.glob("okf_kit-*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
    assert "okf_kit/agent_assets/skills/okf-author/SKILL.md" in names
    assert "okf_kit/agent_assets/skills/okf-search/SKILL.md" in names
    assert "okf_kit/agent_assets/skills/okf-code/SKILL.md" in names

    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=True,
        capture_output=True,
        text=True,
    )
    python = venv / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )
    source = subprocess.run(
        [
            str(python),
            "-c",
            "import okf_kit, pathlib; print(pathlib.Path(okf_kit.__file__).resolve())",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(venv) in source.stdout
    project = tmp_path / "project"
    project.mkdir()
    dry = subprocess.run(
        [
            str(venv / "bin" / "okf"),
            "agent",
            "install",
            "codex",
            "--scope",
            "project",
            "--dry-run",
        ],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "would write .codex/skills/okf-author/SKILL.md" in dry.stdout
    install = subprocess.run(
        [str(venv / "bin" / "okf"), "agent", "install", "codex", "--scope", "project"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "wrote .codex/skills/okf-search/SKILL.md" in install.stdout
    assert (project / ".codex" / "skills" / "okf-author" / "SKILL.md").is_file()
