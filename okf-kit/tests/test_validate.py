"""Tests for okf_kit.core.validate — SPEC §11 conformance (REQ-BM-04, REQ-API-01..04)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import okf_kit.core.validate as validate_module
import yaml
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


def test_hive_profile_separates_conformance_from_publishability(tmp_path):
    _w(tmp_path, "concept.md", "---\ntype: Note\ntitle: Concept\ndescription: d\n---\nbody\n")
    report = validate_bundle(tmp_path, profile="hive")
    assert report.conformant is True
    assert report.publishable is False
    assert report.publication_errors


def test_hive_profile_schema_copy_matches_canonical_contract():
    schema_path = (
        Path(validate_module.__file__).with_name("schemas")
        / "hive-publication-profile.v1.schema.json"
    )
    payload = schema_path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == (
        "0abc13242fc82eec2a11bbc7936a3f36518a6449a840afe782a1be18f53b8a19"
    )
    assert json.loads(payload) == validate_module._HIVE_PROFILE_SCHEMA


def test_hive_profile_shared_conformance_cases(tmp_path):
    fixture = json.loads(
        (
            Path(__file__).with_name("fixtures")
            / "hive-publication-conformance.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture["schema_version"] == "hive-publication-conformance/v1"

    for case in fixture["cases"]:
        metadata = copy.deepcopy(fixture["base"])
        if removed := case.get("remove"):
            metadata.pop(removed)
        for dotted_path, value in case.get("set", {}).items():
            target = metadata
            segments = dotted_path.split(".")
            for segment in segments[:-1]:
                target = target.setdefault(segment, {})
            target[segments[-1]] = value
        concept = "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\nbody\n"
        _w(tmp_path, "concept.md", concept)

        report = validate_bundle(tmp_path, profile="hive")
        local_errors = [
            finding
            for finding in report.publication_errors
            if finding.code != "hive-external-publication-required"
        ]
        assert (not local_errors) is case["valid"], case["name"]
        assert report.publishable is False
        assert len(_codes(report.publication_errors, "hive-external-publication-required")) == 1


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


def test_okf_v02_fields_are_known_not_extension_keys(tmp_path):
    """The five OKF v0.2 fields (SPEC §5) are recognized frontmatter, not
    unknown extension keys — regression guard for _KNOWN_FRONTMATTER_KEYS."""
    _w(
        tmp_path,
        "a.md",
        "---\n"
        "type: T\n"
        "title: A\n"
        "description: d.\n"
        "status: draft\n"
        "stale_after: '2027-01-01'\n"
        "sources: [{id: s1, resource: 'https://example.com'}]\n"
        "generated: {by: 'agent/model', at: '2026-07-01T00:00:00Z'}\n"
        "verified: [{by: 'human:dep', at: '2026-07-02T00:00:00Z'}]\n"
        "---\n"
        "body\n",
    )
    r = validate_bundle(tmp_path)
    assert not _codes(r.info, "extension-key")
    assert r.conformant


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


def test_okf_version_v01_present_emits_mismatch_not_missing(tmp_path):
    """A v0.1 bundle (this validator now supports v0.2) is not "missing" its
    version — it correctly gets a mismatch info finding instead, and stays
    conformant (0 errors): version mismatch is soft guidance, not a block."""
    _w(tmp_path, "index.md", "---\nokf_version: '0.1'\n---\n# Root\n")
    _w(tmp_path, "a.md", "---\ntype: T\ntitle: A\ndescription: d.\n---\nx\n")
    r = validate_bundle(tmp_path)
    assert not _codes(r.info, "okf-version-missing")
    assert _codes(r.info, "okf-version-mismatch")
    assert r.conformant


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
