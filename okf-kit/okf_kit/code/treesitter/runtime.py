"""Runtime adapter over tree-sitter-language-pack."""
from __future__ import annotations

import builtins
from typing import Any, cast


def parse_source(language: str, source: str) -> Any:
    parser = _parser(language)
    return parser.parse(source)


def root_node(tree: Any) -> Any:
    value = tree.root_node
    return value() if callable(value) else value


def node_kind(node: Any) -> str:
    try:
        value = node.type
    except AttributeError:
        value = node.kind
    resolved = value() if callable(value) else value
    return str(resolved)


def children(node: Any) -> list[Any]:
    return [node.child(idx) for idx in range(child_count(node))]


def child_count(node: Any) -> int:
    value = node.child_count
    resolved = value() if callable(value) else value
    return int(resolved)


def child_by_field_name(node: Any, field: str) -> Any | None:
    value = node.child_by_field_name(field)
    return value


def node_text(node: Any, source_bytes: bytes) -> str:
    try:
        text = node.text
    except AttributeError:
        text = None
    if text is not None:
        value = text() if callable(text) else text
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)
    start, end = byte_range(node)
    return source_bytes[start:end].decode("utf-8", errors="replace")


def byte_range(node: Any) -> tuple[int, int]:
    try:
        value = node.byte_range
    except AttributeError:
        value = None
    if value is not None:
        byte_range_value: Any = value() if callable(value) else value
        if hasattr(byte_range_value, "start") and hasattr(byte_range_value, "end"):
            return int(byte_range_value.start), int(byte_range_value.end)
        start, end = cast(tuple[int, int], byte_range_value)
        return int(start), int(end)
    return int(node.start_byte), int(node.end_byte)


def start_line(node: Any) -> int:
    return _point_row(_node_start(node)) + 1


def end_line(node: Any) -> int:
    return _point_row(_node_end(node)) + 1


def first_descendant_text(node: Any, source_bytes: bytes, kinds: tuple[str, ...]) -> str | None:
    if node_kind(node) in kinds:
        return node_text(node, source_bytes)
    for child in children(node):
        found = first_descendant_text(child, source_bytes, kinds)
        if found is not None:
            return found
    return None


def _parser(language: str) -> Any:
    try:
        pack = builtins.__import__("tree_sitter_language_pack", fromlist=["get_parser"])
    except ModuleNotFoundError as exc:
        raise ValueError(
            "Tree-sitter parser support is not installed; install okf-kit[treesitter]"
        ) from exc
    return pack.get_parser(language)


def _node_start(node: Any) -> Any:
    try:
        value = node.start_point
    except AttributeError:
        value = node.start_position
    return value() if callable(value) else value


def _node_end(node: Any) -> Any:
    try:
        value = node.end_point
    except AttributeError:
        value = node.end_position
    return value() if callable(value) else value


def _point_row(point: Any) -> int:
    if hasattr(point, "row"):
        return int(point.row)
    return int(point[0])
