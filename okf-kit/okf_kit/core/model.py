"""Core data model for OKF concepts."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Concept:
    """One OKF concept: a Markdown file with YAML frontmatter + body.

    Attributes:
        cid: concept id — file path relative to the bundle root, no ``.md``
            (e.g. ``tables/users.md`` -> ``tables/users``). Empty for the
            bundle-root reserved files.
        path: absolute path to the ``.md`` file on disk.
        root: absolute path to the bundle root.
        frontmatter: all parsed frontmatter keys (including unknown/extension
            keys); ``{}`` when absent or unparseable. Keys are preserved for
            round-tripping (SPEC §4.1 / REQ-CONS-04).
        body: raw Markdown body (no frontmatter).
        reserved: ``'index'`` / ``'log'`` for reserved filenames, else ``None``.
        frontmatter_error: set when a frontmatter block was present but invalid
            (non-mapping or unparseable YAML). ``None`` when clean or when no
            block was present. The *validator* turns a present-but-invalid block
            into a conformance error (SPEC §4.1 / REQ-CONS-03).
        frontmatter_present: ``True`` when the file opened with a ``---`` block
            (even an empty one); ``False`` when no block was found. Lets the
            validator tell "missing frontmatter" from "present but empty".
    """

    cid: str
    path: Path
    root: Path
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    reserved: str | None = None
    frontmatter_error: str | None = None
    frontmatter_present: bool = False
