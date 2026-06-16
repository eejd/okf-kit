"""Tests for okf_kit.core.validate — SPEC §9 conformance (REQ-BM-04, REQ-API-01..04)."""
from __future__ import annotations

from pathlib import Path

from okf_kit.core.validate import Finding, Report, validate_bundle


def _w(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _codes(findings: list[Finding], code: str) -> list[Finding]:
    return [f for f in findings if f.code == code]


def test_conformant_bundle(tmp_path):
    users = "---\ntype: Table\ntitle: Users\ndescription: Users table.\n---\nbody\n"
    _w(tmp_path, "tables/users.md", users)
    r = validate_bundle(tmp_path)
    assert isinstance(r, Report)
    assert r.conformant is True
    assert r.errors == []


def test_missing_frontmatter_is_error(tmp_path):
    _w(tmp_path, "a.md", "no frontmatter\n")
    r = validate_bundle(tmp_path)
    assert not r.conformant
    assert _codes(r.errors, "frontmatter-missing")


def test_empty_type_is_error(tmp_path):
    _w(tmp_path, "a.md", "---\ntitle: A\n---\nbody\n")
    r = validate_bundle(tmp_path)
    assert not r.conformant
    assert _codes(r.errors, "type-empty")


def test_non_mapping_frontmatter_is_error(tmp_path):
    _w(tmp_path, "a.md", "---\n- x\n---\nbody\n")
    r = validate_bundle(tmp_path)
    assert not r.conformant
    assert _codes(r.errors, "frontmatter-invalid")


def test_missing_recommended_fields_are_warnings(tmp_path):
    _w(tmp_path, "a.md", "---\ntype: T\n---\nbody\n")  # no title/description
    r = validate_bundle(tmp_path)
    assert r.conformant  # warnings don't break conformance
    codes = {f.code for f in r.warnings}
    assert "missing-title" in codes
    assert "missing-description" in codes


def test_extension_key_is_info(tmp_path):
    _w(tmp_path, "a.md", "---\ntype: T\ntitle: A\ndescription: d.\nowner: team\n---\nbody\n")
    r = validate_bundle(tmp_path)
    assert _codes(r.info, "extension-key")


def test_broken_link_is_warning(tmp_path):
    _w(tmp_path, "a.md", "---\ntype: T\ntitle: A\ndescription: d.\n---\n[ghost](ghost.md)\n")
    r = validate_bundle(tmp_path)
    assert _codes(r.warnings, "broken-link")


def test_reserved_index_files_not_required_type(tmp_path):
    _w(tmp_path, "index.md", "# Root\n")
    _w(tmp_path, "tables/index.md", "# Tables\n")
    _w(tmp_path, "tables/users.md", "---\ntype: Table\ntitle: U\ndescription: d.\n---\nx\n")
    r = validate_bundle(tmp_path)
    assert r.conformant, r.errors


def test_nested_index_with_frontmatter_is_info_not_error(tmp_path):
    _w(tmp_path, "sub/index.md", "---\nokf_version: '0.1'\n---\n# Sub\n")
    _w(tmp_path, "sub/a.md", "---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n")
    r = validate_bundle(tmp_path)
    assert r.conformant  # forward-compat: nested index frontmatter is info, not error
    assert _codes(r.info, "nested-index-frontmatter")


def test_empty_bundle_info(tmp_path):
    _w(tmp_path, "index.md", "# Root\n")
    r = validate_bundle(tmp_path)
    assert _codes(r.info, "empty-bundle")


def test_missing_okf_version_is_info(tmp_path):
    _w(tmp_path, "a.md", "---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n")
    r = validate_bundle(tmp_path)
    assert _codes(r.info, "okf-version-missing")


def test_okf_version_present_no_missing_info(tmp_path):
    _w(tmp_path, "index.md", "---\nokf_version: '0.1'\n---\n# Root\n")
    _w(tmp_path, "a.md", "---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n")
    r = validate_bundle(tmp_path)
    assert not _codes(r.info, "okf-version-missing")


def test_okf_version_mismatch_is_info(tmp_path):
    _w(tmp_path, "index.md", "---\nokf_version: '0.9'\n---\n# Root\n")
    _w(tmp_path, "a.md", "---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n")
    r = validate_bundle(tmp_path)
    assert _codes(r.info, "okf-version-mismatch")


def test_invalid_cid_is_warning(tmp_path):
    # filename with a space -> cid violates SPEC §2.2, unaddressable but not an error
    _w(tmp_path, "has space.md", "---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n")
    r = validate_bundle(tmp_path)
    assert _codes(r.warnings, "invalid-cid")
