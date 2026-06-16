"""Tests for okf_kit.cli — the `okf` CLI (subcommands, --json, exit codes)."""
from __future__ import annotations

import json
from pathlib import Path

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
