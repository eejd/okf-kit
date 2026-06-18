"""Path and concept-id helpers for generated code concepts."""
from __future__ import annotations

import re
from pathlib import Path

from okf_kit.core.links import cid_segments_valid, is_within


def concept_id(source_path: str) -> str:
    path = Path(source_path)
    parts = ["code", *path.parts]
    safe = [_safe_segment(part) for part in parts]
    cid = "/".join(safe)
    if not cid_segments_valid(cid):
        raise ValueError(f"unable to derive valid concept id for source path: {source_path}")
    return cid


def concept_path(bundle: Path, cid: str) -> Path:
    candidate = (bundle / f"{cid}.md").resolve()
    if not is_within(candidate.parent, bundle):
        raise ValueError(f"concept path escapes bundle: {cid}")
    return candidate


def _safe_segment(segment: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", segment).strip(".-")
    if not safe:
        safe = "_"
    if not re.match(r"[A-Za-z0-9_]", safe):
        safe = f"_{safe}"
    return safe
