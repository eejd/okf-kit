"""Shared Tree-sitter language adapter."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from okf_kit.code.model import CodeModule, CodeSymbol
from okf_kit.code.treesitter import runtime
from okf_kit.core.links import is_within

_NAME_NODE_KINDS = (
    "identifier",
    "field_identifier",
    "name",
    "package_identifier",
    "type_identifier",
    "simple_identifier",
    "property_identifier",
    "bareword",
    "package",
    "tag_name",
)


@dataclass(frozen=True)
class LanguageAdapter:
    language: str
    parser_name: str
    extensions: tuple[str, ...]
    symbol_kinds: dict[str, str]
    import_kinds: tuple[str, ...]
    parser_by_extension: dict[str, str] | None = None

    def extract(self, path: Path, repo_root: Path) -> CodeModule:
        repo = Path(repo_root).resolve()
        source_path = Path(path).resolve()
        if not is_within(source_path, repo):
            raise ValueError(f"source path escapes repository: {path}")
        if source_path.suffix.lower() not in self.extensions:
            raise ValueError(f"unsupported {self.language} source path: {path}")

        text = source_path.read_text(encoding="utf-8")
        source_bytes = text.encode("utf-8")
        tree = runtime.parse_source(self._parser_name(source_path), text)
        root = runtime.root_node(tree)
        symbols: list[CodeSymbol] = []
        imports: set[str] = set()
        self._walk(root, source_bytes, symbols, imports)
        return CodeModule(
            source_path=source_path.relative_to(repo).as_posix(),
            language=self.language,
            source_hash=hashlib.sha256(source_bytes).hexdigest(),
            imports=tuple(sorted(imports)),
            symbols=tuple(sorted(symbols, key=lambda s: (s.start_line, s.kind, s.name))),
        )

    def _walk(
        self,
        node: object,
        source_bytes: bytes,
        symbols: list[CodeSymbol],
        imports: set[str],
    ) -> None:
        kind = runtime.node_kind(node)
        if kind in self.symbol_kinds:
            name = self._symbol_name(node, source_bytes)
            if name is not None:
                symbols.append(
                    CodeSymbol(
                        kind=self.symbol_kinds[kind],
                        name=name,
                        start_line=runtime.start_line(node),
                        end_line=runtime.end_line(node),
                    )
                )
        if kind in self.import_kinds:
            imports.update(_clean_imports(runtime.node_text(node, source_bytes)))
        for child in runtime.children(node):
            self._walk(child, source_bytes, symbols, imports)

    def _symbol_name(self, node: object, source_bytes: bytes) -> str | None:
        named = runtime.child_by_field_name(node, "name")
        if named is not None:
            return runtime.node_text(named, source_bytes)
        return runtime.first_descendant_text(node, source_bytes, _NAME_NODE_KINDS)

    def _parser_name(self, path: Path) -> str:
        if self.parser_by_extension is None:
            return self.parser_name
        return self.parser_by_extension.get(path.suffix.lower(), self.parser_name)


def _clean_imports(text: str) -> tuple[str, ...]:
    text = " ".join(text.strip().rstrip(";").split())
    module_specifier = re.match(
        r"import(?:\s+type)?(?:\s+.+?\s+from\s+)?\s*['\"]([^'\"]+)['\"]",
        text,
    )
    if module_specifier:
        return (module_specifier.group(1),)
    from_import = re.match(r"from\s+([A-Za-z0-9_.]+)\s+import\s+(.+)", text)
    if from_import:
        module = from_import.group(1)
        raw_names = from_import.group(2).split(",")
        names = [part.strip().split(" as ", maxsplit=1)[0] for part in raw_names]
        names = [name for name in names if name and name != "*"]
        if names:
            if module.strip(".") == "":
                return tuple(f"{module}{name}" for name in names)
            return tuple(f"{module}.{name}" for name in names)
        return (module,)
    direct_import = re.match(r"import\s+(.+)", text)
    if direct_import:
        names = [
            part.strip().split(" as ", maxsplit=1)[0]
            for part in direct_import.group(1).split(",")
        ]
        names = [name.strip("\"'") for name in names if name]
        if names:
            return tuple(names)
    text = re.sub(r"^(import|from|using|use)\s+", "", text)
    text = re.sub(r"\s+from\s+", " from ", text)
    return (text.strip("\"'"),)
