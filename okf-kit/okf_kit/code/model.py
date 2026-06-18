"""Data model for source-code facts rendered as OKF concepts."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeSymbol:
    kind: str
    name: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class CodeRelationship:
    label: str
    target_cid: str


@dataclass(frozen=True)
class CodeModule:
    source_path: str
    language: str
    source_hash: str
    imports: tuple[str, ...]
    symbols: tuple[CodeSymbol, ...]
    relationships: tuple[CodeRelationship, ...] = ()


@dataclass(frozen=True)
class IndexResult:
    written: int
    updated: int
    skipped: int
