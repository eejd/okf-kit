"""Bundle scaffolding and per-type concept templates (REQ-ED-05, REQ-PROD-08).

``init_bundle`` creates a new bundle root with ``okf_version``; ``create_concept``
writes a concept from a built-in type template. Concept ids are validated against
the SPEC §2.2 segment regex, which also guarantees the written path stays inside
the bundle root (no ``..`` or absolute segments).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from okf_kit.core.links import cid_segments_valid, is_within

TEMPLATE_TYPES = ["Table", "Metric", "Runbook", "Playbook", "API"]

_BODY_TEMPLATES: dict[str, str] = {
    "Table": "# Schema\n\n| Column | Type | Description |\n|---|---|---|\n\n# Examples\n\n",
    "Metric": "# Definition\n\n\n# Examples\n\n",
    "Runbook": "# Steps\n\n1. \n\n# Examples\n\n",
    "Playbook": "# Steps\n\n1. \n\n# Examples\n\n",
    "API": "# Endpoints\n\n\n# Examples\n\n",
    "_generic": "# Overview\n\n\n# Examples\n\n",
}


def init_bundle(root: Path, okf_version: str = "0.1", name: str | None = None) -> Path:
    """Create a bundle root with a root ``index.md`` declaring ``okf_version``."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.md"
    fm = yaml.safe_dump({"okf_version": okf_version}, sort_keys=False).strip()
    heading = name if name else root.name
    body = f"# {heading}\n"
    index_path.write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")
    return index_path


def create_concept(
    root: Path,
    cid: str,
    type: str,
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    body: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a new concept from a type template. Raises if the id is invalid or exists."""
    if not cid_segments_valid(cid):
        raise ValueError(f"invalid concept id: {cid!r}")
    root_resolved = Path(root).resolve()
    candidate = root_resolved / f"{cid}.md"
    # Containment on the WRITE path (mirrors resolve_cid_path on the read path):
    # reject a cid whose parent resolves outside the root, e.g. a symlinked dir.
    if not is_within(candidate.parent.resolve(), root_resolved):
        raise ValueError(f"concept path escapes bundle: {cid!r}")

    frontmatter: dict[str, Any] = {"type": type}
    if title is not None:
        frontmatter["title"] = title
    if description is not None:
        frontmatter["description"] = description
    if tags is not None:
        frontmatter["tags"] = list(tags)
    if extra:
        frontmatter.update(extra)

    body_text = body if body is not None else _BODY_TEMPLATES.get(type, _BODY_TEMPLATES["_generic"])
    candidate.parent.mkdir(parents=True, exist_ok=True)
    # O_CREAT|O_EXCL: atomic create — fails if the file appears between the
    # containment check and the write (no TOCTOU clobber of an existing concept).
    with candidate.open("x", encoding="utf-8") as handle:
        handle.write(_render(frontmatter, body_text))
    return candidate


def _render(frontmatter: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_text}\n---\n{body}"
