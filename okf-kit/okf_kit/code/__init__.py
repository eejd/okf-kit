"""Codebase indexing support for OKF."""
from __future__ import annotations

from okf_kit.code.indexer import extract_module, index_codebase
from okf_kit.code.model import CodeModule, CodeSymbol, IndexResult

__all__ = ["CodeModule", "CodeSymbol", "IndexResult", "extract_module", "index_codebase"]
