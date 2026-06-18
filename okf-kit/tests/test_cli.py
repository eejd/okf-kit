"""Tests for okf_kit.cli — the `okf` CLI (subcommands, --json, exit codes)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from okf_kit.cli import main


def _run(args: list[str], capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_init_creates_bundle(tmp_path: Path, capsys):
    root = tmp_path / "kb"
    code, _, _ = _run(["init", str(root)], capsys)
    assert code == 0
    assert (root / "index.md").exists()


def test_new_validate_read_roundtrip(tmp_path: Path, capsys):
    root = tmp_path / "kb"
    _run(["init", str(root)], capsys)

    code, _, _ = _run(
        ["new", str(root), "Table", "tables/users", "--title", "Users", "--desc", "User accounts."],
        capsys,
    )
    assert code == 0
    assert (root / "tables" / "users.md").exists()

    code, _, _ = _run(["validate", str(root)], capsys)
    assert code == 0  # conformant

    code, out, _ = _run(["read", str(root), "tables/users"], capsys)
    assert code == 0
    assert "Users" in out


def test_validate_nonconformant_exits_1(tmp_path: Path, capsys):
    (tmp_path / "bad.md").write_text("no frontmatter\n", encoding="utf-8")
    code, _, _ = _run(["validate", str(tmp_path)], capsys)
    assert code == 1


def test_validate_json_output(tmp_path: Path, capsys):
    (tmp_path / "index.md").write_text("---\nokf_version: '0.1'\n---\n# Root\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n", encoding="utf-8")
    code, out, _ = _run(["validate", str(tmp_path), "--json"], capsys)
    assert code == 0
    data = json.loads(out)
    assert data["conformant"] is True


def test_read_missing_exits_2(tmp_path: Path, capsys):
    (tmp_path / "a.md").write_text("---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n", encoding="utf-8")
    code, _, err = _run(["read", str(tmp_path), "nope"], capsys)
    assert code == 2
    assert "not found" in err.lower()


def test_search_prints_hit(tmp_path: Path, capsys):
    (tmp_path / "index.md").write_text("---\nokf_version: '0.1'\n---\n# Root\n", encoding="utf-8")
    (tmp_path / "a.md").write_text(
        "---\ntype: Table\ntitle: Customer Orders\ndescription: d.\n---\norders\n", encoding="utf-8"
    )
    code, out, _ = _run(["search", str(tmp_path), "orders"], capsys)
    assert code == 0
    assert "Customer Orders" in out


def test_index_regen(tmp_path: Path, capsys):
    (tmp_path / "index.md").write_text("---\nokf_version: '0.1'\n---\n# Root\n", encoding="utf-8")
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "users.md").write_text("---\ntype: Table\ntitle: Users\ndescription: d.\n---\nx\n", encoding="utf-8")
    code, _, _ = _run(["index", "regen", str(tmp_path)], capsys)
    assert code == 0
    assert (tables / "index.md").exists()


def test_code_index_help(capsys):
    code, out, _ = _run(["code", "index", "--help"], capsys)
    assert code == 0
    assert "source code" in out
    assert "okf-kit[treesitter]" in out
    assert "--language" in out
    assert "--update" in out
    assert "typescript" in out
    assert "rust" in out
    assert "go" in out
    assert "csharp" in out
    assert "php" in out


def test_code_index_missing_dependency_exits_2(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
):
    import okf_kit.code.indexer as indexer

    def missing(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("Tree-sitter parser support is not installed; install okf-kit[treesitter]")

    monkeypatch.setattr(indexer, "index_codebase", missing)
    code, _, err = _run(["code", "index", str(tmp_path), str(tmp_path / "kb")], capsys)
    assert code == 2
    assert "okf-kit[treesitter]" in err


def test_code_index_io_error_exits_2(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch):
    import okf_kit.code.indexer as indexer

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr(indexer, "index_codebase", fail)
    code, _, err = _run(["code", "index", str(tmp_path), str(tmp_path / "kb")], capsys)
    assert code == 2
    assert "disk full" in err


def test_code_index_writes_valid_searchable_bundle(tmp_path: Path, capsys):
    pytest.importorskip("tree_sitter_language_pack")
    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "service.py").write_text(
        "class Greeter:\n"
        "    def greet(self) -> str:\n"
        "        return 'hello'\n"
        "\n"
        "def normalize(value: str) -> str:\n"
        "    return value.strip()\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"

    code, out, _ = _run(["code", "index", str(repo), str(bundle)], capsys)
    assert code == 0
    assert "indexed code: wrote" in out
    assert (bundle / "code" / "pkg" / "service.py.md").is_file()

    code, _, _ = _run(["validate", str(bundle)], capsys)
    assert code == 0
    code, out, _ = _run(["search", str(bundle), "Greeter"], capsys)
    assert code == 0
    assert "pkg/service.py" in out


def test_code_index_refreshes_generated_concepts_by_default(tmp_path: Path, capsys):
    pytest.importorskip("tree_sitter_language_pack")
    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    service = package / "service.py"
    service.write_text("class Greeter:\n    pass\n", encoding="utf-8")
    bundle = tmp_path / "kb"

    code, _, _ = _run(["code", "index", str(repo), str(bundle)], capsys)
    assert code == 0
    service.write_text(
        "class Greeter:\n    pass\n\ndef new_helper():\n    return None\n",
        encoding="utf-8",
    )

    code, out, _ = _run(["code", "index", str(repo), str(bundle)], capsys)
    assert code == 0
    assert "updated 1" in out
    assert "new_helper" in (bundle / "code" / "pkg" / "service.py.md").read_text(
        encoding="utf-8"
    )


def test_agent_install_help(capsys):
    code, out, _ = _run(["agent", "install", "--help"], capsys)
    assert code == 0
    assert "claude-code" in out
    assert "codex" in out
    assert "--scope" in out
    assert "--dry-run" in out
    assert "--update" in out


@pytest.mark.parametrize(
    ("target", "skill_prefix", "manifest_rel"),
    [
        ("claude-code", ".claude/skills", ".claude/okf-agent-assets.json"),
        ("codex", ".codex/skills", ".codex/okf-agent-assets.json"),
    ],
)
def test_agent_install_project_dry_run(
    tmp_path: Path,
    capsys,
    monkeypatch,
    target: str,
    skill_prefix: str,
    manifest_rel: str,
):
    monkeypatch.chdir(tmp_path)
    code, out, _ = _run(["agent", "install", target, "--scope", "project", "--dry-run"], capsys)
    assert code == 0
    assert f"would write {skill_prefix}/okf-author/SKILL.md" in out
    assert f"would write {skill_prefix}/okf-search/SKILL.md" in out
    assert f"would write {skill_prefix}/okf-code/SKILL.md" in out
    assert f"would write {manifest_rel}" in out
    assert not (tmp_path / skill_prefix.split("/", maxsplit=1)[0]).exists()


@pytest.mark.parametrize(
    ("target", "skill_prefix", "manifest_rel"),
    [
        ("claude-code", ".claude/skills", ".claude/okf-agent-assets.json"),
        ("codex", ".codex/skills", ".codex/okf-agent-assets.json"),
    ],
)
def test_agent_install_project_writes_files(
    tmp_path: Path,
    capsys,
    monkeypatch,
    target: str,
    skill_prefix: str,
    manifest_rel: str,
):
    monkeypatch.chdir(tmp_path)
    code, out, _ = _run(["agent", "install", target, "--scope", "project"], capsys)
    assert code == 0
    assert f"wrote {skill_prefix}/okf-author/SKILL.md" in out
    assert f"wrote {skill_prefix}/okf-search/SKILL.md" in out
    assert f"wrote {skill_prefix}/okf-code/SKILL.md" in out
    assert f"wrote {manifest_rel}" in out
    assert (tmp_path / skill_prefix / "okf-author" / "SKILL.md").is_file()
    assert (tmp_path / skill_prefix / "okf-search" / "SKILL.md").is_file()
    assert (tmp_path / skill_prefix / "okf-code" / "SKILL.md").is_file()
    manifest = json.loads((tmp_path / manifest_rel).read_text(encoding="utf-8"))
    assert manifest["target"] == target
    assert manifest["scope"] == "project"


def test_agent_install_unmanaged_file_exits_2(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("local\n", encoding="utf-8")

    code, _, err = _run(["agent", "install", "codex", "--scope", "project", "--update"], capsys)
    assert code == 2
    assert "unmanaged" in err


def test_agent_install_refuses_okf_bundle_root(tmp_path: Path, capsys, monkeypatch):
    bundle = tmp_path / "kb"
    code, _, _ = _run(["init", str(bundle)], capsys)
    assert code == 0

    monkeypatch.chdir(bundle)
    code, _, err = _run(["agent", "install", "codex", "--scope", "project"], capsys)
    assert code == 2
    assert "inside an OKF bundle" in err
    assert not (bundle / ".codex").exists()

    code, _, _ = _run(["validate", str(bundle)], capsys)
    assert code == 0


def test_agent_install_refuses_okf_bundle_subdirectory(tmp_path: Path, capsys, monkeypatch):
    bundle = tmp_path / "kb"
    code, _, _ = _run(["init", str(bundle)], capsys)
    assert code == 0
    subdir = bundle / "notes"
    subdir.mkdir()

    monkeypatch.chdir(subdir)
    code, _, err = _run(["agent", "install", "codex", "--scope", "project"], capsys)
    assert code == 2
    assert "inside an OKF bundle" in err
    assert not (subdir / ".codex").exists()
    assert not (bundle / ".codex").exists()

    code, _, _ = _run(["validate", str(bundle)], capsys)
    assert code == 0


def test_agent_install_nonwritable_project_root_exits_2(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tmp_path.chmod(0o500)
    try:
        code, _, err = _run(["agent", "install", "codex", "--scope", "project"], capsys)
    finally:
        tmp_path.chmod(0o700)

    assert code == 2
    assert "ownership manifest" in err
    assert not (tmp_path / ".codex").exists()
