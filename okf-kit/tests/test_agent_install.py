"""Tests for installing OKF agent skill assets."""
from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import okf_kit.agent_install as agent_install
import pytest
from okf_kit.agent_install import install_agent_assets, manifest_path, skill_root


@pytest.mark.parametrize(
    ("target", "skill_prefix", "manifest_rel"),
    [
        ("claude-code", ".claude/skills", ".claude/okf-agent-assets.json"),
        ("codex", ".codex/skills", ".codex/okf-agent-assets.json"),
    ],
)
def test_project_dry_run_does_not_write(
    tmp_path: Path,
    target: str,
    skill_prefix: str,
    manifest_rel: str,
):
    actions = install_agent_assets(tmp_path, target, scope="project", dry_run=True)

    assert f"would write {skill_prefix}/okf-author/SKILL.md" in [a.message for a in actions]
    assert f"would write {skill_prefix}/okf-search/SKILL.md" in [a.message for a in actions]
    assert f"would write {manifest_rel}" in [a.message for a in actions]
    assert not (tmp_path / skill_prefix.split("/", maxsplit=1)[0]).exists()


@pytest.mark.parametrize(
    ("target", "skill_prefix", "manifest_rel"),
    [
        ("claude-code", ".claude/skills", ".claude/okf-agent-assets.json"),
        ("codex", ".codex/skills", ".codex/okf-agent-assets.json"),
    ],
)
def test_project_install_writes_skills_and_manifest(
    tmp_path: Path,
    target: str,
    skill_prefix: str,
    manifest_rel: str,
):
    actions = install_agent_assets(tmp_path, target, scope="project")

    messages = [a.message for a in actions]
    assert f"wrote {skill_prefix}/okf-author/SKILL.md" in messages
    assert f"wrote {skill_prefix}/okf-search/SKILL.md" in messages
    assert f"wrote {manifest_rel}" in messages
    assert (tmp_path / skill_prefix / "okf-author" / "SKILL.md").is_file()
    assert (tmp_path / skill_prefix / "okf-search" / "SKILL.md").is_file()
    manifest = json.loads((tmp_path / manifest_rel).read_text())
    assert manifest["target"] == target
    assert manifest["scope"] == "project"
    assert f"{skill_prefix}/okf-author/SKILL.md" in manifest["files"]
    assert f"{skill_prefix}/okf-search/SKILL.md" in manifest["files"]


def test_user_scope_targets_documented_skill_roots_and_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    install_agent_assets(tmp_path / "project", "claude-code", scope="user")
    install_agent_assets(tmp_path / "project", "codex", scope="user")

    assert (tmp_path / "home" / ".claude" / "skills" / "okf-author" / "SKILL.md").is_file()
    assert (tmp_path / "home" / ".codex" / "skills" / "okf-search" / "SKILL.md").is_file()
    claude_manifest = json.loads(
        (tmp_path / "home" / ".claude" / "okf-agent-assets.json").read_text()
    )
    codex_manifest = json.loads((tmp_path / "home" / ".codex" / "okf-agent-assets.json").read_text())
    assert claude_manifest["target"] == "claude-code"
    assert claude_manifest["scope"] == "user"
    assert codex_manifest["target"] == "codex"
    assert codex_manifest["scope"] == "user"


def test_existing_owned_file_updates_by_default_with_matching_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    install_agent_assets(tmp_path, "codex", scope="project")
    first = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    original = first.read_text(encoding="utf-8")

    assets = agent_install._assets()
    changed_text = original + "\nChanged asset.\n"
    changed_assets = [
        replace(asset, text=changed_text, digest=sha256(changed_text.encode()).hexdigest())
        if asset.rel == Path("okf-author") / "SKILL.md"
        else asset
        for asset in assets
    ]
    monkeypatch.setattr(agent_install, "_assets", lambda: changed_assets)
    monkeypatch.setattr(
        agent_install,
        "LEGACY_ASSET_DIGESTS",
        {"okf-author/SKILL.md": frozenset({sha256(original.encode()).hexdigest()})},
    )

    updated = install_agent_assets(tmp_path, "codex", scope="project")
    assert "updated .codex/skills/okf-author/SKILL.md" in [a.message for a in updated]
    assert first.read_text(encoding="utf-8") == changed_text

    skipped = install_agent_assets(tmp_path, "codex", scope="project", update=False)
    assert "skipped .codex/skills/okf-author/SKILL.md" in [a.message for a in skipped]
    assert first.read_text(encoding="utf-8") == changed_text


def test_legacy_manifest_migrates_existing_skills_and_adds_new_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    author = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    search = tmp_path / ".codex" / "skills" / "okf-search" / "SKILL.md"
    author.parent.mkdir(parents=True)
    search.parent.mkdir(parents=True)
    author.write_text("old author\n", encoding="utf-8")
    search.write_text("old search\n", encoding="utf-8")
    author_digest = sha256(author.read_bytes()).hexdigest()
    search_digest = sha256(search.read_bytes()).hexdigest()
    manifest = manifest_path(tmp_path, "codex", "project")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "target": "codex",
                "scope": "project",
                "version": "1",
                "files": {
                    ".codex/skills/okf-author/SKILL.md": {"sha256": author_digest},
                    ".codex/skills/okf-search/SKILL.md": {"sha256": search_digest},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        agent_install,
        "LEGACY_ASSET_DIGESTS",
        {
            "okf-author/SKILL.md": frozenset({author_digest}),
            "okf-search/SKILL.md": frozenset({search_digest}),
        },
    )

    actions = install_agent_assets(tmp_path, "codex", scope="project")

    messages = [action.message for action in actions]
    assert "updated .codex/skills/okf-author/SKILL.md" in messages
    assert "updated .codex/skills/okf-search/SKILL.md" in messages
    assert "wrote .codex/skills/okf-code/SKILL.md" in messages
    assert "old author" not in author.read_text(encoding="utf-8")
    assert "old search" not in search.read_text(encoding="utf-8")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert ".codex/skills/okf-code/SKILL.md" in data["files"]


def test_update_refuses_hash_mismatch_as_unmanaged(tmp_path: Path):
    install_agent_assets(tmp_path, "codex", scope="project")
    skill = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    skill.write_text("user edit\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unmanaged"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)

    assert skill.read_text(encoding="utf-8") == "user edit\n"


def test_existing_owned_file_read_error_is_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    install_agent_assets(tmp_path, "codex", scope="project")
    skill = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == skill:
            raise PermissionError("blocked")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    with pytest.raises(ValueError, match="unable to read file"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)


def test_spoofed_manifest_digest_does_not_mark_file_owned(tmp_path: Path):
    skill = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("malicious\n", encoding="utf-8")
    digest = sha256(skill.read_bytes()).hexdigest()
    manifest = manifest_path(tmp_path, "codex", "project")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "target": "codex",
                "scope": "project",
                "version": "1",
                "files": {".codex/skills/okf-author/SKILL.md": {"sha256": digest}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unmanaged"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)

    assert skill.read_text(encoding="utf-8") == "malicious\n"


def test_existing_file_without_manifest_is_unmanaged(tmp_path: Path):
    skill = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("local\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unmanaged"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)


def test_existing_skill_directory_is_unmanaged(tmp_path: Path):
    skill = tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md"
    skill.mkdir(parents=True)

    with pytest.raises(ValueError, match="unmanaged"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)

    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()


def test_malformed_manifest_is_unmanaged(tmp_path: Path):
    install_agent_assets(tmp_path, "codex", scope="project")
    manifest_path(tmp_path, "codex", "project").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)


def test_manifest_directory_is_invalid_manifest(tmp_path: Path):
    manifest_path(tmp_path, "codex", "project").mkdir(parents=True)

    with pytest.raises(ValueError, match="invalid ownership manifest"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "skills").exists()


@pytest.mark.parametrize(("field", "value"), [("target", "claude-code"), ("scope", "user")])
def test_manifest_target_scope_mismatch_refuses(tmp_path: Path, field: str, value: str):
    install_agent_assets(tmp_path, "codex", scope="project")
    manifest = manifest_path(tmp_path, "codex", "project")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data[field] = value
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="target/scope"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)


def test_non_allowlisted_manifest_entry_is_refused(tmp_path: Path):
    install_agent_assets(tmp_path, "codex", scope="project")
    manifest = manifest_path(tmp_path, "codex", "project")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["files"][".codex/skills/local/SKILL.md"] = {"sha256": "x"}
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest contains unmanaged path"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)


@pytest.mark.parametrize("bad_path", ["/tmp/okf/SKILL.md", ".codex/../evil.md"])
def test_invalid_manifest_paths_are_refused(tmp_path: Path, bad_path: str):
    install_agent_assets(tmp_path, "codex", scope="project")
    manifest = manifest_path(tmp_path, "codex", "project")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["files"][bad_path] = {"sha256": "x"}
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest path"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)


def test_symlink_escape_refuses_before_writing(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = skill_root(tmp_path, "codex", "project")
    root.parent.mkdir(parents=True)
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported")

    with pytest.raises(ValueError, match="escapes"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()
    assert not (outside / "okf-author").exists()


def test_nested_skill_symlink_refuses_before_writing(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = skill_root(tmp_path, "codex", "project")
    (root).mkdir(parents=True)
    try:
        (root / "okf-author").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported")

    with pytest.raises(ValueError, match="symlink"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()
    assert not (outside / "SKILL.md").exists()


def test_manifest_symlink_refuses_before_writing(tmp_path: Path):
    manifest = manifest_path(tmp_path, "codex", "project")
    manifest.parent.mkdir(parents=True)
    try:
        manifest.symlink_to(tmp_path / ".codex" / "skills" / "okf-author" / "SKILL.md")
    except OSError:
        pytest.skip("symlinks not supported")

    with pytest.raises(ValueError, match="symlink"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "skills").exists()


def test_manifest_parent_symlink_refuses_before_reading(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "okf-agent-assets.json").write_text("{}", encoding="utf-8")
    try:
        (tmp_path / ".codex").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported")

    with pytest.raises(ValueError, match="symlink"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "skills").exists()


def test_regular_file_parent_refuses_before_writing(tmp_path: Path):
    parent = tmp_path / ".codex" / "skills" / "okf-search"
    parent.parent.mkdir(parents=True)
    parent.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "skills" / "okf-author").exists()
    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()


def test_manifest_temp_directory_refuses_before_writing(tmp_path: Path):
    temp = tmp_path / ".codex" / ".okf-agent-assets.json.tmp"
    temp.mkdir(parents=True)

    with pytest.raises(ValueError, match="temporary manifest path"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "skills").exists()
    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()


def test_existing_manifest_temp_file_refuses_before_writing(tmp_path: Path):
    temp = tmp_path / ".codex" / ".okf-agent-assets.json.tmp"
    temp.parent.mkdir(parents=True)
    temp.write_text("stale\n", encoding="utf-8")
    temp.chmod(0o400)

    with pytest.raises(ValueError, match="temporary manifest path"):
        install_agent_assets(tmp_path, "codex", scope="project")

    assert not (tmp_path / ".codex" / "skills").exists()
    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()


def test_unwritable_manifest_parent_refuses_before_writing_skills(tmp_path: Path):
    manifest_parent = tmp_path / ".codex"
    manifest_parent.mkdir()
    manifest_parent.chmod(0o500)
    try:
        with pytest.raises(ValueError, match="ownership manifest"):
            install_agent_assets(tmp_path, "codex", scope="project")
    finally:
        manifest_parent.chmod(0o700)

    assert not (tmp_path / ".codex" / "skills").exists()
    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()


def test_unwritable_second_skill_parent_rolls_back_first_skill(tmp_path: Path):
    blocked = tmp_path / ".codex" / "skills" / "okf-search"
    blocked.mkdir(parents=True)
    blocked.chmod(0o500)
    try:
        with pytest.raises(ValueError, match="skill asset"):
            install_agent_assets(tmp_path, "codex", scope="project")
    finally:
        blocked.chmod(0o700)

    assert not (tmp_path / ".codex" / "skills" / "okf-author").exists()
    assert not (tmp_path / ".codex" / "skills" / "okf-search" / "SKILL.md").exists()
    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()


def test_refusal_after_first_planned_write_has_no_side_effects(tmp_path: Path):
    unmanaged = tmp_path / ".codex" / "skills" / "okf-search" / "SKILL.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text("local\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unmanaged"):
        install_agent_assets(tmp_path, "codex", scope="project", update=True)

    assert not (tmp_path / ".codex" / "skills" / "okf-author").exists()
    assert not (tmp_path / ".codex" / "okf-agent-assets.json").exists()
