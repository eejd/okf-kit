"""index.md regeneration (REQ-BM-05, REQ-PROD-05, SPEC §6).

Generates a per-directory ``index.md`` — concepts grouped by ``type`` with
title + description, plus subdirectory links — for every directory that
contains a concept anywhere in its subtree. Root ``index.md`` preserves an
existing ``okf_version``; non-root indexes are body-only (SPEC §2.5).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from okf_kit.core.links import iter_concept_files
from okf_kit.core.model import Concept
from okf_kit.core.parse import parse_concept, split_frontmatter


def regenerate_indexes(root: Path) -> list[Path]:
    """Write/overwrite ``index.md`` in each directory containing concepts."""
    root = Path(root).resolve()
    all_md = list(iter_concept_files(root))
    concepts = [parse_concept(md, root) for md in all_md]
    concept_files = [c for c in concepts if c.reserved is None]

    # Every directory that has a concept in its subtree (incl. root) gets an index.
    target_dirs: set[Path] = set()
    for concept in concept_files:
        directory = concept.path.parent
        while True:
            target_dirs.add(directory)
            if directory == root:
                break
            directory = directory.parent

    written: list[Path] = []
    for directory in sorted(target_dirs):
        children = [c for c in concept_files if c.path.parent == directory]
        subdirs = sorted(s for s in target_dirs if s.parent == directory and s != directory)
        index_path = directory / "index.md"
        index_path.write_text(_render_index(directory, root, children, subdirs), encoding="utf-8")
        written.append(index_path)
    return written


def _render_index(
    directory: Path, root: Path, children: list[Concept], subdirs: list[Path]
) -> str:
    lines: list[str] = []

    if directory == root:
        version = _existing_okf_version(directory / "index.md")
        if version is not None:
            fm = yaml.safe_dump({"okf_version": version}, sort_keys=False).strip()
            lines.append(f"---\n{fm}\n---")

    by_type: dict[str, list[Concept]] = {}
    for concept in children:
        type_value = concept.frontmatter.get("type")
        key = type_value if isinstance(type_value, str) and type_value else "Concept"
        by_type.setdefault(key, []).append(concept)

    for type_key in sorted(by_type):
        lines.append("")
        lines.append(f"# {type_key}")
        for concept in sorted(by_type[type_key], key=lambda c: c.cid):
            title = _str_field(concept, "title") or concept.cid.rsplit("/", 1)[-1]
            entry = f"- [{title}]({concept.path.name})"
            description = _str_field(concept, "description")
            if description:
                entry += f" — {description}"
            lines.append(entry)

    if subdirs:
        lines.append("")
        lines.append("# Subdirectories")
        for sub in subdirs:
            lines.append(f"- [{sub.name}]({sub.name}/index.md)")

    return "\n".join(lines) + "\n"


def _str_field(concept: Concept, key: str) -> str:
    value = concept.frontmatter.get(key)
    return value if isinstance(value, str) else ""


def _existing_okf_version(index_path: Path) -> str | None:
    if not index_path.is_file():
        return None
    result = split_frontmatter(index_path.read_text(encoding="utf-8"))
    version: Any = result.data.get("okf_version")
    return version if isinstance(version, str) else None
