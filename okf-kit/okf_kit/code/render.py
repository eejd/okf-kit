"""Render source-code facts as OKF Markdown concepts."""
from __future__ import annotations

import yaml

from okf_kit.code.managed import MANAGED_END, MANAGED_START
from okf_kit.code.model import CodeModule, CodeRelationship, CodeSymbol


def render_concept(module: CodeModule) -> str:
    frontmatter = {
        "type": "CodeModule",
        "title": module.source_path,
        "description": f"Generated code map for {module.source_path}.",
        "resource": module.source_path,
        "tags": ["code", module.language],
        "source_path": module.source_path,
        "language": module.language,
        "source_hash": module.source_hash,
        "managed_by": "okf-code",
    }
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_text}\n---\n{_managed_body(module)}"


def _managed_body(module: CodeModule) -> str:
    return (
        f"{MANAGED_START}\n"
        "# Overview\n\n"
        f"Generated CodeModule concept for `{module.source_path}`. This page is "
        "syntax-derived from source code and is intended for documentation, code "
        "finding, code-logic search, and impact-analysis groundwork.\n\n"
        "# Symbols\n\n"
        f"{_symbols_table(module.symbols)}\n\n"
        "# Relationships\n\n"
        f"{_relationships_list(module.relationships, module.imports)}\n\n"
        "# Impact notes\n\n"
        "Impact candidates on this page are syntax-derived. Treat them as a "
        "starting point for inspection, not as complete semantic proof of all "
        "callers, callees, or runtime effects.\n\n"
        "# Citations\n\n"
        f"- Source: `{module.source_path}`\n"
        f"- Source hash: `{module.source_hash}`\n"
        f"{MANAGED_END}\n"
    )


def _symbols_table(symbols: tuple[CodeSymbol, ...]) -> str:
    if not symbols:
        return "No classes, functions, methods, or elements detected."
    rows = ["| Kind | Name | Lines |", "|---|---|---|"]
    for symbol in symbols:
        rows.append(f"| {symbol.kind} | `{symbol.name}` | {symbol.start_line}-{symbol.end_line} |")
    return "\n".join(rows)


def _relationships_list(
    relationships: tuple[CodeRelationship, ...],
    imports: tuple[str, ...],
) -> str:
    rows: list[str] = []
    for relationship in relationships:
        rows.append(f"- [{relationship.label}](/{relationship.target_cid}.md)")
    linked_labels = {relationship.label for relationship in relationships}
    for name in imports:
        if name not in linked_labels:
            rows.append(f"- `{name}`")
    if not rows:
        return "No imports detected."
    return "\n".join(rows)
