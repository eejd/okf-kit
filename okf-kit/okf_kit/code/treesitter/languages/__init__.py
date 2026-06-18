"""Language adapters for Tree-sitter-backed code indexing."""
from __future__ import annotations

from okf_kit.code.treesitter.languages.base import LanguageAdapter

ADAPTERS: dict[str, LanguageAdapter] = {
    "python": LanguageAdapter(
        language="python",
        parser_name="python",
        extensions=(".py",),
        symbol_kinds={"class_definition": "class", "function_definition": "function"},
        import_kinds=("import_statement", "import_from_statement", "future_import_statement"),
    ),
    "javascript": LanguageAdapter(
        language="javascript",
        parser_name="javascript",
        extensions=(".js", ".jsx", ".mjs", ".cjs"),
        symbol_kinds={
            "class_declaration": "class",
            "function_declaration": "function",
            "method_definition": "method",
            "variable_declarator": "function",
        },
        import_kinds=("import_statement",),
        parser_by_extension={".tsx": "tsx"},
    ),
    "typescript": LanguageAdapter(
        language="typescript",
        parser_name="typescript",
        extensions=(".ts", ".tsx", ".mts", ".cts"),
        symbol_kinds={
            "class_declaration": "class",
            "interface_declaration": "interface",
            "function_declaration": "function",
            "method_definition": "method",
            "variable_declarator": "function",
        },
        import_kinds=("import_statement",),
    ),
    "java": LanguageAdapter(
        language="java",
        parser_name="java",
        extensions=(".java",),
        symbol_kinds={
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "method_declaration": "method",
        },
        import_kinds=("import_declaration",),
    ),
    "scala": LanguageAdapter(
        language="scala",
        parser_name="scala",
        extensions=(".scala",),
        symbol_kinds={
            "class_definition": "class",
            "object_definition": "object",
            "trait_definition": "trait",
            "function_definition": "function",
        },
        import_kinds=("import_declaration",),
    ),
    "rust": LanguageAdapter(
        language="rust",
        parser_name="rust",
        extensions=(".rs",),
        symbol_kinds={
            "struct_item": "struct",
            "enum_item": "enum",
            "trait_item": "trait",
            "impl_item": "impl",
            "function_item": "function",
        },
        import_kinds=("use_declaration",),
    ),
    "go": LanguageAdapter(
        language="go",
        parser_name="go",
        extensions=(".go",),
        symbol_kinds={
            "type_spec": "type",
            "function_declaration": "function",
            "method_declaration": "method",
        },
        import_kinds=("import_declaration", "import_spec"),
    ),
    "kotlin": LanguageAdapter(
        language="kotlin",
        parser_name="kotlin",
        extensions=(".kt", ".kts"),
        symbol_kinds={
            "class_declaration": "class",
            "object_declaration": "object",
            "function_declaration": "function",
        },
        import_kinds=("import_header",),
    ),
    "perl": LanguageAdapter(
        language="perl",
        parser_name="perl",
        extensions=(".pl", ".pm", ".t"),
        symbol_kinds={
            "package_statement": "package",
            "subroutine_declaration_statement": "function",
        },
        import_kinds=("use_statement", "require_expression"),
    ),
    "csharp": LanguageAdapter(
        language="csharp",
        parser_name="csharp",
        extensions=(".cs",),
        symbol_kinds={
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "method_declaration": "method",
        },
        import_kinds=("using_directive",),
    ),
    "php": LanguageAdapter(
        language="php",
        parser_name="php",
        extensions=(".php", ".phtml"),
        symbol_kinds={
            "class_declaration": "class",
            "interface_declaration": "interface",
            "trait_declaration": "trait",
            "method_declaration": "method",
            "function_definition": "function",
        },
        import_kinds=("namespace_use_declaration",),
    ),
    "html": LanguageAdapter(
        language="html",
        parser_name="html",
        extensions=(".html", ".htm"),
        symbol_kinds={"element": "element"},
        import_kinds=("script_element", "style_element"),
    ),
}

__all__ = ["ADAPTERS", "LanguageAdapter"]
