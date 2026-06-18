"""Install packaged OKF agent skill assets for supported agent clients."""
from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from okf_kit.core.parse import split_frontmatter

Target = Literal["claude-code", "codex"]
Scope = Literal["project", "user"]

ASSET_VERSION = "1"
SKILL_NAMES = ("okf-author", "okf-search", "okf-code")
LEGACY_ASSET_DIGESTS: dict[str, frozenset[str]] = {
    "okf-author/SKILL.md": frozenset(
        {
            "624c4ef881f783e4a03b6128aca42b9ab04791eb89544b3a7dbd68d35c857b6c",
            "825ea861cab759c0c0100d3903e6554af8b9c10fc5d760969d6cf91c5b40d524",
        }
    ),
    "okf-search/SKILL.md": frozenset(
        {
            "3d9e0a1d8a9901092960977a17df77f1869561adde11f262d18ade8e60560e44",
        }
    ),
}


@dataclass(frozen=True)
class InstallAction:
    """One planned or completed installer action."""

    status: str
    path: str
    message: str


@dataclass(frozen=True)
class _Asset:
    rel: Path
    text: str
    digest: str


@dataclass(frozen=True)
class _TargetPaths:
    base: Path
    skill_root: Path
    manifest: Path


@dataclass(frozen=True)
class _StagedSkillWrite:
    temp: Path
    dest: Path
    previous: bytes | None


def install_agent_assets(
    project_root: Path,
    target: str,
    *,
    scope: Scope = "project",
    dry_run: bool = False,
    update: bool = True,
) -> list[InstallAction]:
    """Install OKF-owned skill assets for ``target``.

    The full plan is validated before any directory, file, or manifest write.
    Existing files are updated only when the current file digest matches the
    OKF ownership manifest.
    """
    typed_target = _check_target(target)
    typed_scope = _check_scope(scope)
    paths = _target_paths(Path(project_root), typed_target, typed_scope)
    if typed_scope == "project" and _inside_okf_bundle(paths.base):
        raise ValueError("refusing to install agent assets inside an OKF bundle")
    assets = _assets()
    target_assets = [_asset_for_target(paths, asset) for asset in assets]
    allowlist = {asset.rel.as_posix() for asset in target_assets}
    _preflight_paths(paths)
    manifest = _read_manifest(paths.manifest, typed_target, typed_scope, allowlist, paths)
    actions = _plan_actions(paths, assets, manifest, dry_run=dry_run, update=update)
    manifest_action = _manifest_action(paths, dry_run=dry_run)
    if dry_run:
        return [*actions, manifest_action]

    temp_manifest = _stage_manifest(paths, typed_target, typed_scope, target_assets, actions)
    staged_skills: list[_StagedSkillWrite] = []
    created_skill_dirs: list[Path] = []
    committed_skills: list[_StagedSkillWrite] = []
    committed = False
    try:
        staged_skills, created_skill_dirs = _stage_skill_writes(paths, actions, target_assets)
        committed_skills = _commit_skill_writes(staged_skills)
        _commit_manifest(paths, temp_manifest)
        committed = True
    except ValueError:
        _rollback_committed_skill_writes(committed_skills)
        _remove_empty_dirs(created_skill_dirs)
        raise
    finally:
        with suppress(OSError):
            if not committed and temp_manifest.exists():
                temp_manifest.unlink()
    return [*actions, manifest_action]


def skill_root(project_root: Path, target: str, scope: Scope) -> Path:
    """Return the configured skill root for tests and callers."""
    return _target_paths(Path(project_root), _check_target(target), _check_scope(scope)).skill_root


def manifest_path(project_root: Path, target: str, scope: Scope) -> Path:
    """Return the configured manifest path for tests and callers."""
    return _target_paths(Path(project_root), _check_target(target), _check_scope(scope)).manifest


def _check_target(target: str) -> Target:
    if target not in {"claude-code", "codex"}:
        raise ValueError("target must be one of: claude-code, codex")
    return target  # type: ignore[return-value]


def _check_scope(scope: str) -> Scope:
    if scope not in {"project", "user"}:
        raise ValueError("scope must be one of: project, user")
    return scope  # type: ignore[return-value]


def _target_paths(project_root: Path, target: Target, scope: Scope) -> _TargetPaths:
    base = Path.home() if scope == "user" else project_root
    if target == "claude-code":
        skill_rel = Path(".claude") / "skills"
        manifest_rel = Path(".claude") / "okf-agent-assets.json"
    else:
        skill_rel = Path(".codex") / "skills"
        manifest_rel = Path(".codex") / "okf-agent-assets.json"
    return _TargetPaths(base=base, skill_root=base / skill_rel, manifest=base / manifest_rel)


def _is_okf_bundle_root(path: Path) -> bool:
    index = path / "index.md"
    if not index.is_file():
        return False
    try:
        result = split_frontmatter(index.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"unable to read OKF bundle index: {index}") from exc
    return result.present and isinstance(result.data.get("okf_version"), str)


def _inside_okf_bundle(path: Path) -> bool:
    current = path.resolve(strict=False)
    return any(_is_okf_bundle_root(candidate) for candidate in (current, *current.parents))


def _assets() -> list[_Asset]:
    root = resources.files("okf_kit").joinpath("agent_assets", "skills")
    assets: list[_Asset] = []
    for skill in SKILL_NAMES:
        text = root.joinpath(skill, "SKILL.md").read_text(encoding="utf-8")
        rel = Path(skill) / "SKILL.md"
        # Relativize against the install base for each target later.
        assets.append(_Asset(rel=rel, text=text, digest=_sha256_text(text)))
    return assets


def _asset_for_target(paths: _TargetPaths, asset: _Asset) -> _Asset:
    rel = paths.skill_root.relative_to(paths.base) / asset.rel
    return _Asset(rel=rel, text=asset.text, digest=asset.digest)


def _plan_actions(
    paths: _TargetPaths,
    raw_assets: list[_Asset],
    manifest: dict[str, str] | None,
    *,
    dry_run: bool,
    update: bool,
) -> list[InstallAction]:
    _preflight_paths(paths)
    assets = [_asset_for_target(paths, asset) for asset in raw_assets]
    for asset in assets:
        _validate_relative_asset_path(asset.rel)
        dest = paths.base / asset.rel
        _ensure_confined(paths.skill_root, dest)
        _preflight_no_symlinks(paths.skill_root, dest)
        _preflight_directory_components(paths.base, dest.parent)
    _ensure_confined(paths.manifest.parent, paths.manifest)
    _preflight_no_symlinks(paths.manifest.parent, paths.manifest)

    actions: list[InstallAction] = []
    for asset, source_asset in zip(assets, raw_assets, strict=True):
        dest = paths.base / asset.rel
        display = asset.rel.as_posix()
        exists = dest.exists() or dest.is_symlink()
        if exists:
            _preflight_no_symlinks(paths.base, dest)
            if not dest.is_file():
                raise ValueError(f"unmanaged existing file: {display}")
            if manifest is None:
                raise ValueError(f"unmanaged existing file: {display}")
            recorded = manifest.get(display)
            current = _sha256_file(dest)
            if (
                recorded is None
                or current != recorded
                or current not in _known_asset_digests(source_asset)
            ):
                raise ValueError(f"unmanaged existing file: {display}")
            if not update:
                actions.append(InstallAction("skip", display, f"skipped {display}"))
            else:
                verb = "would update" if dry_run else "updated"
                actions.append(InstallAction("update", display, f"{verb} {display}"))
        else:
            verb = "would write" if dry_run else "wrote"
            actions.append(InstallAction("write", display, f"{verb} {display}"))
    return actions


def _read_manifest(
    path: Path,
    target: Target,
    scope: Scope,
    allowlist: set[str],
    paths: _TargetPaths,
) -> dict[str, str] | None:
    if not path.exists():
        if path.is_symlink():
            raise ValueError(f"path escapes install base through symlink: {path}")
        return None
    if path.is_symlink():
        raise ValueError(f"path escapes install base through symlink: {path}")
    if not path.is_file():
        raise ValueError(f"invalid ownership manifest: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"invalid ownership manifest: {path}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid ownership manifest: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("invalid ownership manifest")
    if raw.get("target") != target or raw.get("scope") != scope:
        raise ValueError("ownership manifest target/scope mismatch")
    files = raw.get("files")
    if not isinstance(files, dict):
        raise ValueError("invalid ownership manifest")

    parsed: dict[str, str] = {}
    for rel, entry in files.items():
        if not isinstance(rel, str) or not isinstance(entry, dict):
            raise ValueError("invalid ownership manifest")
        digest = entry.get("sha256")
        if not isinstance(digest, str):
            raise ValueError("invalid ownership manifest")
        _validate_relative_manifest_path(rel)
        if rel not in allowlist:
            raise ValueError(f"manifest contains unmanaged path: {rel}")
        _ensure_confined(paths.skill_root, paths.base / rel)
        parsed[rel] = digest
    return parsed


def _manifest_action(paths: _TargetPaths, *, dry_run: bool) -> InstallAction:
    rel = paths.manifest.relative_to(paths.base).as_posix()
    verb = "would write" if dry_run else "wrote"
    return InstallAction("manifest", rel, f"{verb} {rel}")


def _stage_skill_writes(
    paths: _TargetPaths,
    actions: list[InstallAction],
    assets: list[_Asset],
) -> tuple[list[_StagedSkillWrite], list[Path]]:
    staged: list[_StagedSkillWrite] = []
    created_dirs: list[Path] = []
    current_dest = paths.skill_root
    try:
        for action, asset in zip(actions, assets, strict=True):
            if action.status not in {"write", "update"}:
                continue
            current_dest = paths.base / asset.rel
            created_dirs.extend(_missing_dirs(current_dest.parent))
            current_dest.parent.mkdir(parents=True, exist_ok=True)
            temp = current_dest.with_name(f".{current_dest.name}.okf-tmp")
            _ensure_confined(current_dest.parent, temp)
            _preflight_no_symlinks(current_dest.parent, temp)
            if temp.exists() or temp.is_symlink():
                raise ValueError(f"temporary skill path already exists: {temp}")
            previous = current_dest.read_bytes() if action.status == "update" else None
            with temp.open("x", encoding="utf-8") as temp_file:
                temp_file.write(asset.text)
            staged.append(_StagedSkillWrite(temp=temp, dest=current_dest, previous=previous))
    except OSError as exc:
        _cleanup_staged_skill_writes(staged)
        _remove_empty_dirs(created_dirs)
        raise ValueError(f"unable to write skill asset: {current_dest}") from exc
    except ValueError:
        _cleanup_staged_skill_writes(staged)
        _remove_empty_dirs(created_dirs)
        raise
    return staged, created_dirs


def _commit_skill_writes(staged: list[_StagedSkillWrite]) -> list[_StagedSkillWrite]:
    committed: list[_StagedSkillWrite] = []
    try:
        for staged_write in staged:
            staged_write.temp.replace(staged_write.dest)
            committed.append(staged_write)
    except OSError as exc:
        _cleanup_staged_skill_writes(staged)
        _rollback_committed_skill_writes(committed)
        raise ValueError(f"unable to write skill asset: {staged_write.dest}") from exc
    return committed


def _cleanup_staged_skill_writes(staged: list[_StagedSkillWrite]) -> None:
    for staged_write in staged:
        with suppress(OSError):
            if staged_write.temp.exists() or staged_write.temp.is_symlink():
                staged_write.temp.unlink()


def _rollback_committed_skill_writes(committed: list[_StagedSkillWrite]) -> None:
    for staged_write in reversed(committed):
        with suppress(OSError):
            if staged_write.previous is None:
                if staged_write.dest.exists() or staged_write.dest.is_symlink():
                    staged_write.dest.unlink()
            else:
                staged_write.dest.write_bytes(staged_write.previous)


def _missing_dirs(path: Path) -> list[Path]:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    return list(reversed(missing))


def _remove_empty_dirs(paths: list[Path]) -> None:
    for path in reversed(paths):
        with suppress(OSError):
            path.rmdir()


def _stage_manifest(
    paths: _TargetPaths,
    target: Target,
    scope: Scope,
    assets: list[_Asset],
    actions: list[InstallAction],
) -> Path:
    file_digests: dict[str, dict[str, str]] = {}
    for asset, action in zip(assets, actions, strict=True):
        digest = _sha256_file(paths.base / asset.rel) if action.status == "skip" else asset.digest
        file_digests[asset.rel.as_posix()] = {"sha256": digest}
    data: dict[str, Any] = {
        "version": ASSET_VERSION,
        "target": target,
        "scope": scope,
        "files": file_digests,
    }
    try:
        paths.manifest.parent.mkdir(parents=True, exist_ok=True)
        temp = _manifest_temp_path(paths)
        _preflight_manifest_temp(paths)
        with temp.open("x", encoding="utf-8") as temp_file:
            temp_file.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        raise ValueError(f"unable to write ownership manifest: {paths.manifest}") from exc
    return temp


def _commit_manifest(paths: _TargetPaths, temp: Path) -> None:
    try:
        temp.replace(paths.manifest)
    except OSError as exc:
        raise ValueError(f"unable to write ownership manifest: {paths.manifest}") from exc


def _validate_relative_asset_path(path: Path) -> None:
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"invalid packaged asset path: {path.as_posix()}")


def _validate_relative_manifest_path(path: str) -> None:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"invalid manifest path: {path}")


def _known_asset_digests(asset: _Asset) -> set[str]:
    return {asset.digest, *LEGACY_ASSET_DIGESTS.get(asset.rel.as_posix(), frozenset())}


def _manifest_temp_path(paths: _TargetPaths) -> Path:
    return paths.manifest.with_name(f".{paths.manifest.name}.tmp")


def _preflight_paths(paths: _TargetPaths) -> None:
    _preflight_root(paths.base, paths.skill_root)
    _preflight_root(paths.base, paths.manifest.parent)
    _ensure_confined(paths.manifest.parent, paths.manifest)
    _preflight_no_symlinks(paths.manifest.parent, paths.manifest)
    _preflight_manifest_temp(paths)


def _preflight_manifest_temp(paths: _TargetPaths) -> None:
    temp = _manifest_temp_path(paths)
    _ensure_confined(paths.manifest.parent, temp)
    _preflight_no_symlinks(paths.manifest.parent, temp)
    if temp.exists() or temp.is_symlink():
        raise ValueError(f"temporary manifest path already exists: {temp}")


def _preflight_root(base: Path, root: Path) -> None:
    _ensure_confined(base, root)
    _preflight_no_symlinks(base, root)
    _preflight_directory_components(base, root)


def _preflight_no_symlinks(base: Path, path: Path) -> None:
    base_abs = base.absolute()
    path_abs = path.absolute()
    try:
        rel = path_abs.relative_to(base_abs)
    except ValueError as exc:
        raise ValueError(f"path escapes install base: {path}") from exc
    current = base_abs
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"path escapes install base through symlink: {current}")


def _preflight_directory_components(base: Path, path: Path) -> None:
    base_abs = base.absolute()
    path_abs = path.absolute()
    try:
        rel = path_abs.relative_to(base_abs)
    except ValueError as exc:
        raise ValueError(f"path escapes install base: {path}") from exc
    current = base_abs
    for part in rel.parts:
        current = current / part
        if current.exists() and not current.is_dir():
            raise ValueError(f"path component is not a directory: {current}")


def _ensure_confined(base: Path, path: Path) -> None:
    base_resolved = base.resolve(strict=False)
    path_resolved = path.resolve(strict=False)
    try:
        path_resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes install base: {path}") from exc


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f"unable to read file: {path}") from exc
