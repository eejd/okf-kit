"""Repository walking and language selection for code indexing."""
from __future__ import annotations

from pathlib import Path

from okf_kit.code.treesitter.languages import ADAPTERS, LanguageAdapter
from okf_kit.core.links import is_within

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
    "target",
    "venv",
}


def adapters_for(languages: list[str] | None) -> list[LanguageAdapter]:
    if not languages:
        return [ADAPTERS[language] for language in sorted(ADAPTERS)]
    unknown = sorted(set(languages) - set(ADAPTERS))
    if unknown:
        supported = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"unsupported language(s): {', '.join(unknown)} (supported: {supported})")
    return [ADAPTERS[language] for language in languages]


def language_help() -> str:
    return ", ".join(sorted(ADAPTERS))


def iter_source_files(repo: Path, bundle: Path, adapters: list[LanguageAdapter]) -> list[Path]:
    extensions = {ext for adapter in adapters for ext in adapter.extensions}
    files: list[Path] = []
    for path in sorted(repo.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        rel_parts = path.relative_to(repo).parts
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel_parts):
            continue
        resolved = path.resolve()
        if is_within(resolved, bundle):
            continue
        files.append(resolved)
    return files


def adapter_for_path(path: Path, adapters: list[LanguageAdapter]) -> LanguageAdapter:
    for adapter in adapters:
        if path.suffix.lower() in adapter.extensions:
            return adapter
    raise ValueError(f"unsupported source file extension: {path.suffix}")
