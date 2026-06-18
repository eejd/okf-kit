"""Index source-code repositories into OKF CodeModule concepts."""
from __future__ import annotations

import posixpath
from dataclasses import replace
from pathlib import Path

from okf_kit.code.discovery import adapter_for_path, adapters_for, iter_source_files
from okf_kit.code.managed import merge_managed, split_generated
from okf_kit.code.model import CodeModule, CodeRelationship, IndexResult
from okf_kit.code.paths import concept_id, concept_path
from okf_kit.code.render import render_concept
from okf_kit.core.links import is_within
from okf_kit.core.parse import split_frontmatter
from okf_kit.core.templates import init_bundle


def extract_module(path: Path, repo_root: Path, *, language: str | None = None) -> CodeModule:
    """Extract syntax-level facts from one source file."""
    adapters = adapters_for([language] if language else None)
    adapter = adapter_for_path(Path(path), adapters)
    return adapter.extract(Path(path), Path(repo_root))


def index_codebase(
    repo_root: Path,
    bundle_root: Path,
    *,
    languages: list[str] | None = None,
    update: bool = True,
) -> IndexResult:
    """Index a source repository into OKF CodeModule concepts."""
    adapters = adapters_for(languages)
    repo = Path(repo_root).resolve()
    bundle = Path(bundle_root).resolve()
    if not repo.is_dir():
        raise ValueError(f"repository does not exist: {repo_root}")
    if not (bundle / "index.md").is_file():
        init_bundle(bundle, name=bundle.name)
    else:
        bundle.mkdir(parents=True, exist_ok=True)

    written = 0
    updated = 0
    skipped = 0
    modules: list[CodeModule] = []
    cid_by_source: dict[str, str] = {}
    source_by_cid: dict[str, str] = {}
    for source in iter_source_files(repo, bundle, adapters):
        adapter = adapter_for_path(source, adapters)
        module = adapter.extract(source, repo)
        cid = concept_id(module.source_path)
        existing_source = source_by_cid.get(cid)
        if existing_source is not None and existing_source != module.source_path:
            raise ValueError(
                "duplicate code concept id after path normalization: "
                f"{existing_source} and {module.source_path} both map to {cid}"
            )
        modules.append(module)
        cid_by_source[module.source_path] = cid
        source_by_cid[cid] = module.source_path

    modules = [_with_relationships(module, cid_by_source) for module in modules]
    _preflight_destinations(bundle, modules, cid_by_source)
    _preflight_existing_concepts(bundle, modules, cid_by_source)
    for module in modules:
        cid = cid_by_source[module.source_path]
        dest = concept_path(bundle, cid)
        if not is_within(dest, bundle):
            raise ValueError(f"concept path escapes bundle: {cid}")
        rendered = render_concept(module)
        if dest.exists():
            if not update:
                skipped += 1
                continue
            existing = dest.read_text(encoding="utf-8")
            dest.write_text(merge_managed(existing, rendered), encoding="utf-8")
            updated += 1
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered, encoding="utf-8")
            written += 1
    return IndexResult(written=written, updated=updated, skipped=skipped)


def _preflight_destinations(
    bundle: Path,
    modules: list[CodeModule],
    cid_by_source: dict[str, str],
) -> None:
    for module in modules:
        dest = concept_path(bundle, cid_by_source[module.source_path])
        current = bundle
        rel_parent = dest.parent.relative_to(bundle)
        for part in rel_parent.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(
                    f"code concept destination escapes bundle through symlink: {current}"
                )
            if current.exists() and not current.is_dir():
                raise ValueError(f"code concept destination parent is not a directory: {current}")
        if dest.exists() and not dest.is_file():
            raise ValueError(f"code concept destination is not a file: {dest}")


def _preflight_existing_concepts(
    bundle: Path,
    modules: list[CodeModule],
    cid_by_source: dict[str, str],
) -> None:
    for module in modules:
        dest = concept_path(bundle, cid_by_source[module.source_path])
        if not dest.exists():
            continue
        existing = dest.read_text(encoding="utf-8")
        frontmatter = split_frontmatter(existing)
        if (
            not frontmatter.present
            or frontmatter.data.get("managed_by") != "okf-code"
            or frontmatter.data.get("source_path") != module.source_path
            or split_generated(existing) is None
        ):
            raise ValueError(
                "refusing to index over existing non-okf-code concept: "
                f"{cid_by_source[module.source_path]}"
            )


def _with_relationships(module: CodeModule, cid_by_source: dict[str, str]) -> CodeModule:
    module_keys = _module_keys(cid_by_source)
    relationships: list[CodeRelationship] = []
    seen: set[str] = set()
    for imported in module.imports:
        target = _resolve_import(imported, module.source_path, module_keys)
        if target is None or target == cid_by_source[module.source_path] or target in seen:
            continue
        relationships.append(CodeRelationship(label=imported, target_cid=target))
        seen.add(target)
    return replace(module, relationships=tuple(relationships))


def _module_keys(cid_by_source: dict[str, str]) -> dict[str, str]:
    keys: dict[str, str] = {}
    for source_path, cid in cid_by_source.items():
        path = Path(source_path)
        stem_path = path.with_suffix("").as_posix()
        dotted = stem_path.replace("/", ".")
        for key in {source_path, stem_path, dotted}:
            keys.setdefault(key, cid)
        if path.name == "__init__.py":
            package = path.parent.as_posix().replace("/", ".")
            if package != ".":
                keys.setdefault(package, cid)
    return keys


def _resolve_import(imported: str, source_path: str, module_keys: dict[str, str]) -> str | None:
    normalized = imported.strip().strip("\"'")
    relative = _relative_import_candidates(normalized, source_path)
    for candidate in relative:
        if candidate in module_keys:
            return module_keys[candidate]
    candidates = [normalized]
    if "." in normalized:
        parts = normalized.split(".")
        candidates.extend(".".join(parts[:idx]) for idx in range(len(parts) - 1, 0, -1))
    if "/" in normalized:
        parts = normalized.split("/")
        candidates.extend("/".join(parts[:idx]) for idx in range(len(parts) - 1, 0, -1))
    for candidate in candidates:
        if candidate in module_keys:
            return module_keys[candidate]
    return None


def _relative_import_candidates(imported: str, source_path: str) -> list[str]:
    if imported.startswith(("./", "../")):
        stem = (Path(source_path).parent / imported).as_posix()
        normalized = posixpath.normpath(stem)
        return [normalized, str(Path(normalized).with_suffix("")), f"{normalized}/index"]
    if not imported.startswith("."):
        return []
    dot_count = len(imported) - len(imported.lstrip("."))
    suffix = imported[dot_count:]
    package_parts = list(Path(source_path).parent.parts)
    if dot_count > 1:
        package_parts = package_parts[: -(dot_count - 1)]
    prefix = ".".join(package_parts)
    dotted = ".".join(part for part in (prefix, suffix) if part)
    candidates = [dotted]
    parts = dotted.split(".")
    candidates.extend(".".join(parts[:idx]) for idx in range(len(parts) - 1, 0, -1))
    return candidates
