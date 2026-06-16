"""Frontmatter splitting and concept parsing (SPEC §4.1, REQ-CONS-01..04).

The parser is permissive: it never raises on malformed input. A missing
frontmatter block degrades gracefully to an empty-mapping concept whose whole
text is the body; a *present-but-invalid* block (non-mapping or unparseable
YAML) records ``frontmatter_error`` so the validator can report it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from okf_kit.core.model import Concept

_DELIMITER = "---"
_RESERVED_FILES = {"index.md": "index", "log.md": "log"}
# Defensive ceiling on a single concept file (DoS guard against huge/symlinked
# files). v0.1 is a local tool; this is belt-and-suspenders, not a hard SLA.
_MAX_CONCEPT_BYTES = 8 * 1024 * 1024


@dataclass
class FrontmatterResult:
    """Outcome of splitting a file's text into frontmatter + body."""

    data: dict[str, Any]
    body: str
    present: bool
    error: str | None


def split_frontmatter(text: str) -> FrontmatterResult:
    """Split ``text`` into ``(frontmatter, body)``.

    A valid block opens with ``---`` on the very first line (no leading
    whitespace, no BOM) and closes with a later line of exactly ``---``.
    """
    if text.startswith("﻿"):
        return FrontmatterResult({}, text, present=False, error=None)

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _DELIMITER:
        return FrontmatterResult({}, text, present=False, error=None)

    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == _DELIMITER:
            close_idx = i
            break
    if close_idx is None:
        return FrontmatterResult({}, text, present=False, error=None)

    fm_text = "".join(lines[1:close_idx])
    body_text = "".join(lines[close_idx + 1 :])

    if fm_text.strip() == "":
        return FrontmatterResult({}, body_text, present=True, error=None)

    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        return FrontmatterResult(
            {}, body_text, present=True, error=f"frontmatter YAML parse error: {exc}"
        )

    if not isinstance(data, dict):
        return FrontmatterResult(
            {},
            body_text,
            present=True,
            error=f"frontmatter must be a YAML mapping, got {type(data).__name__}",
        )

    return FrontmatterResult(data, body_text, present=True, error=None)


def parse_concept(path: Path, root: Path) -> Concept:
    """Parse one ``.md`` file into a :class:`Concept`."""
    path = Path(path)
    root = Path(root)
    rel = path.relative_to(root).as_posix()
    cid = rel[:-3] if rel.endswith(".md") else rel
    reserved = _RESERVED_FILES.get(path.name)

    try:
        size = path.stat().st_size
    except OSError as exc:
        return Concept(
            cid=cid, path=path, root=root, reserved=reserved,
            frontmatter_error=f"cannot stat file: {exc}",
        )
    if size > _MAX_CONCEPT_BYTES:
        return Concept(
            cid=cid, path=path, root=root, reserved=reserved,
            frontmatter_error=f"file too large: {size} bytes (limit {_MAX_CONCEPT_BYTES})",
        )

    text = path.read_text(encoding="utf-8")
    result = split_frontmatter(text)
    return Concept(
        cid=cid,
        path=path,
        root=root,
        frontmatter=result.data,
        body=result.body,
        reserved=reserved,
        frontmatter_error=result.error,
        frontmatter_present=result.present,
    )


def serialize_concept(concept: Concept) -> str:
    """Serialize a :class:`Concept` back to frontmatter + body text.

    Round-trips all frontmatter keys (order preserved). A concept with no
    frontmatter is serialized as body-only.
    """
    parts: list[str] = []
    if concept.frontmatter:
        fm = yaml.safe_dump(
            concept.frontmatter, sort_keys=False, allow_unicode=True
        ).strip()
        parts.append(f"---\n{fm}\n---\n")
    parts.append(concept.body)
    return "".join(parts)
