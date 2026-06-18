"""Tests for Tree-sitter-backed source-code indexing into OKF concepts."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from okf_kit.core.context import read_concept
from okf_kit.core.search import build_index, search
from okf_kit.core.validate import validate_bundle


def _require_tree_sitter_extra() -> None:
    pytest.importorskip("tree_sitter_language_pack")


def _write_python_repo(root: Path) -> None:
    package = root / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "service.py").write_text(
        "\n".join(
            [
                "import json",
                "from pathlib import Path",
                "",
                "class UserService:",
                "    def load_user(self, path: Path) -> dict:",
                "        return json.loads(path.read_text())",
                "",
                "def helper(value: str) -> str:",
                "    return value.strip()",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_extract_python_module_facts_are_deterministic(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import extract_module

    repo = tmp_path / "repo"
    _write_python_repo(repo)

    first = extract_module(repo / "pkg" / "service.py", repo, language="python")
    second = extract_module(repo / "pkg" / "service.py", repo, language="python")

    assert first == second
    assert first.source_path == "pkg/service.py"
    assert first.language == "python"
    assert first.imports == ("json", "pathlib.Path")
    assert [(s.kind, s.name, s.start_line, s.end_line) for s in first.symbols] == [
        ("class", "UserService", 4, 6),
        ("function", "load_user", 5, 6),
        ("function", "helper", 8, 9),
    ]
    assert len(first.source_hash) == 64


def test_index_codebase_writes_valid_searchable_managed_concepts(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    bundle = tmp_path / "kb"
    _write_python_repo(repo)

    result = index_codebase(repo, bundle)

    assert result.written == 2
    assert result.updated == 0
    service = bundle / "code" / "pkg" / "service.py.md"
    assert service.is_file()
    text = service.read_text(encoding="utf-8")
    assert "type: CodeModule" in text
    assert "title: pkg/service.py" in text
    assert "source_path: pkg/service.py" in text
    assert "language: python" in text
    assert "managed_by: okf-code" in text
    assert "# Overview" in text
    assert "# Symbols" in text
    assert "UserService" in text
    assert "load_user" in text
    assert "# Relationships" in text
    assert "json" in text
    assert "# Impact notes" in text
    assert "syntax-derived" in text
    assert "# Citations" in text
    assert "<!-- okf-code:start -->" in text
    assert "<!-- okf-code:end -->" in text

    report = validate_bundle(bundle)
    assert report.conformant, report.to_dict()
    hits = search(build_index(bundle), "UserService")
    assert [hit.cid for hit in hits] == ["code/pkg/service.py"]


def test_index_codebase_preserves_narrative_outside_managed_section(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    bundle = tmp_path / "kb"
    _write_python_repo(repo)
    index_codebase(repo, bundle)

    service = bundle / "code" / "pkg" / "service.py.md"
    original = service.read_text(encoding="utf-8")
    service.write_text(
        original.replace(
            "<!-- okf-code:start -->",
            "# Human preface\n\nKeep this preface.\n\n<!-- okf-code:start -->",
        )
        + "\n# Human notes\n\nKeep this explanation.\n",
        encoding="utf-8",
    )

    (repo / "pkg" / "service.py").write_text(
        (repo / "pkg" / "service.py").read_text(encoding="utf-8")
        + "\ndef normalize_email(value: str) -> str:\n    return value.lower()\n",
        encoding="utf-8",
    )
    result = index_codebase(repo, bundle, update=True)
    updated = service.read_text(encoding="utf-8")

    assert result.updated >= 1
    assert "# Human preface" in updated
    assert "Keep this preface." in updated
    assert "# Human notes" in updated
    assert "Keep this explanation." in updated
    assert "normalize_email" in updated


def test_index_codebase_does_not_overwrite_existing_root_index(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    bundle = tmp_path / "kb"
    _write_python_repo(repo)
    bundle.mkdir()
    (bundle / "index.md").write_text(
        "---\nokf_version: '0.1'\n---\n# Curated root\n\nKeep me.\n",
        encoding="utf-8",
    )

    index_codebase(repo, bundle)

    assert "Keep me." in (bundle / "index.md").read_text(encoding="utf-8")


def test_index_codebase_rejects_normalized_concept_id_collisions(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    (src / "a b.py").write_text("class SpaceName:\n    pass\n", encoding="utf-8")
    (src / "a-b.py").write_text("class DashName:\n    pass\n", encoding="utf-8")
    bundle = tmp_path / "kb"

    with pytest.raises(ValueError, match="duplicate code concept id"):
        index_codebase(repo, bundle, languages=["python"])

    assert not (bundle / "code").exists()


def test_index_codebase_preflights_destination_parent_conflicts_before_writing(
    tmp_path: Path,
):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    (repo / "aaa").mkdir(parents=True)
    (repo / "zzz" / "blocked").mkdir(parents=True)
    (repo / "aaa" / "first.py").write_text("class First:\n    pass\n", encoding="utf-8")
    (repo / "zzz" / "blocked" / "second.py").write_text(
        "class Second:\n    pass\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"
    blocking_parent = bundle / "code" / "zzz" / "blocked"
    blocking_parent.parent.mkdir(parents=True)
    blocking_parent.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(ValueError, match="parent is not a directory"):
        index_codebase(repo, bundle, languages=["python"])

    assert not (bundle / "code" / "aaa" / "first.py.md").exists()


def test_index_codebase_links_resolvable_local_imports_for_depth_reads(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
    (package / "service.py").write_text(
        "from .models import User\n\nclass UserService:\n    pass\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"

    index_codebase(repo, bundle, languages=["python"])

    service = (bundle / "code" / "pkg" / "service.py.md").read_text(encoding="utf-8")
    assert "[.models.User](/code/pkg/models.py.md)" in service
    context = read_concept(bundle, "code/pkg/service.py", depth=1)
    assert "# code/pkg/models.py (depth 1)" in context
    assert "User" in context


def test_index_codebase_links_python_package_relative_imports_without_global_stem_fallback(
    tmp_path: Path,
):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    (repo / "pkg" / "feature").mkdir(parents=True)
    (repo / "other").mkdir(parents=True)
    (repo / "pkg" / "models.py").write_text("class PackageModel:\n    pass\n", encoding="utf-8")
    (repo / "pkg" / "feature" / "models.py").write_text(
        "class FeatureModel:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "other" / "models.py").write_text("class OtherModel:\n    pass\n", encoding="utf-8")
    (repo / "pkg" / "service.py").write_text(
        "from . import models\n\nclass PackageService:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "pkg" / "feature" / "service.py").write_text(
        "from .. import models\n\nclass FeatureService:\n    pass\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"

    index_codebase(repo, bundle, languages=["python"])

    package_context = read_concept(bundle, "code/pkg/service.py", depth=1)
    assert "# code/pkg/models.py (depth 1)" in package_context
    assert "# code/other/models.py (depth 1)" not in package_context
    feature_context = read_concept(bundle, "code/pkg/feature/service.py", depth=1)
    assert "# code/pkg/models.py (depth 1)" in feature_context
    assert "# code/pkg/feature/models.py (depth 1)" not in feature_context


def test_index_codebase_links_grouped_python_relative_imports(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
    (package / "utils.py").write_text("def normalize():\n    return None\n", encoding="utf-8")
    (package / "service.py").write_text(
        "from . import models, utils\n\nclass UserService:\n    pass\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"

    index_codebase(repo, bundle, languages=["python"])

    service = (bundle / "code" / "pkg" / "service.py.md").read_text(encoding="utf-8")
    assert "[.models](/code/pkg/models.py.md)" in service
    assert "[.utils](/code/pkg/utils.py.md)" in service
    context = read_concept(bundle, "code/pkg/service.py", depth=1)
    assert "# code/pkg/models.py (depth 1)" in context
    assert "# code/pkg/utils.py (depth 1)" in context


def test_index_codebase_links_grouped_python_direct_imports(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "models.py").write_text("class User:\n    pass\n", encoding="utf-8")
    (package / "utils.py").write_text("def normalize():\n    return None\n", encoding="utf-8")
    (package / "service.py").write_text(
        "import pkg.models, pkg.utils\n\nclass UserService:\n    pass\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"

    index_codebase(repo, bundle, languages=["python"])

    service = (bundle / "code" / "pkg" / "service.py.md").read_text(encoding="utf-8")
    assert "[pkg.models](/code/pkg/models.py.md)" in service
    assert "[pkg.utils](/code/pkg/utils.py.md)" in service
    context = read_concept(bundle, "code/pkg/service.py", depth=1)
    assert "# code/pkg/models.py (depth 1)" in context
    assert "# code/pkg/utils.py (depth 1)" in context


def test_index_codebase_links_js_relative_imports_for_depth_reads(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    (src / "foo.ts").write_text("export class Foo {}\n", encoding="utf-8")
    (src / "app.ts").write_text(
        'import { Foo } from "./foo";\nclass App { run(): Foo { return new Foo(); } }\n',
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"

    index_codebase(repo, bundle, languages=["typescript"])

    app = (bundle / "code" / "src" / "app.ts.md").read_text(encoding="utf-8")
    assert "[./foo](/code/src/foo.ts.md)" in app
    context = read_concept(bundle, "code/src/app.ts", depth=1)
    assert "# code/src/foo.ts (depth 1)" in context
    assert "Foo" in context


def test_index_codebase_links_js_parent_relative_imports_for_depth_reads(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    (repo / "src" / "components").mkdir(parents=True)
    (repo / "src" / "foo.ts").write_text("export class ParentFoo {}\n", encoding="utf-8")
    (repo / "src" / "components" / "app.ts").write_text(
        'import { ParentFoo } from "../foo";\nclass App { run(): ParentFoo { return new ParentFoo(); } }\n',
        encoding="utf-8",
    )
    bundle = tmp_path / "kb"

    index_codebase(repo, bundle, languages=["typescript"])

    app = (bundle / "code" / "src" / "components" / "app.ts.md").read_text(encoding="utf-8")
    assert "[../foo](/code/src/foo.ts.md)" in app
    context = read_concept(bundle, "code/src/components/app.ts", depth=1)
    assert "# code/src/foo.ts (depth 1)" in context
    assert "ParentFoo" in context


def test_index_codebase_refuses_to_update_unmanaged_existing_concept(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "service.py").write_text("class UserService:\n    pass\n", encoding="utf-8")
    bundle = tmp_path / "kb"
    unmanaged = bundle / "code" / "pkg" / "service.py.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text(
        "---\ntype: Note\ntitle: Hand written\n---\n# Keep this\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-okf-code concept"):
        index_codebase(repo, bundle, languages=["python"], update=True)

    assert unmanaged.read_text(encoding="utf-8") == (
        "---\ntype: Note\ntitle: Hand written\n---\n# Keep this\n"
    )


def test_index_codebase_refuses_to_skip_unmanaged_existing_concept(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    (package / "service.py").write_text("class UserService:\n    pass\n", encoding="utf-8")
    bundle = tmp_path / "kb"
    unmanaged = bundle / "code" / "pkg" / "service.py.md"
    unmanaged.parent.mkdir(parents=True)
    unmanaged.write_text(
        "---\ntype: Note\ntitle: Hand written\n---\n# Keep this\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-okf-code concept"):
        index_codebase(repo, bundle, languages=["python"], update=False)

    assert unmanaged.read_text(encoding="utf-8") == (
        "---\ntype: Note\ntitle: Hand written\n---\n# Keep this\n"
    )


def test_missing_tree_sitter_dependency_error_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import okf_kit.code.treesitter.runtime as runtime

    repo = tmp_path / "repo"
    _write_python_repo(repo)

    real_import = __import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "tree_sitter_language_pack":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "tree_sitter_language_pack", raising=False)
    monkeypatch.setattr(runtime.builtins, "__import__", fake_import)

    with pytest.raises(ValueError, match=r"okf-kit\[treesitter\]"):
        from okf_kit.code.indexer import extract_module

        extract_module(repo / "pkg" / "service.py", repo, language="python")


def test_requested_language_adapters_extract_symbols(tmp_path: Path):
    _require_tree_sitter_extra()
    from okf_kit.code.indexer import index_codebase

    repo = tmp_path / "polyglot"
    (repo / "src").mkdir(parents=True)
    samples = {
        "src/app.py": "class PyService:\n    def run(self):\n        pass\n",
        "src/app.js": "class JsService { run() {} }\nfunction jsHelper() {}\n",
        "src/app.ts": "interface TsShape { x: string }\nclass TsService { run(): void {} }\n",
        "src/card.tsx": "export function Card() { return <div>Hello</div>; }\n",
        "src/App.java": "import java.util.List;\nclass JavaService { void run() {} }\n",
        "src/App.scala": "class ScalaService { def run(): Unit = {} }\nobject ScalaObj {}\n",
        "src/lib.rs": "pub struct RustService;\nimpl RustService { pub fn run(&self) {} }\n",
        "src/main.go": "package main\n\ntype GoService struct{}\nfunc goHelper() {}\n",
        "src/App.kt": "class KotlinService { fun run() {} }\nfun kotlinHelper() {}\n",
        "src/app.pl": "package PerlService;\nsub run { return 1; }\n",
        "src/App.cs": "using System;\nclass CSharpService { void Run() {} }\n",
        "src/app.php": "<?php\nclass PhpService { public function run() {} }\nfunction php_helper() {}\n",
        "src/index.html": "<html><body><main id=\"app\"><h1>Hello</h1></main></body></html>\n",
    }
    for rel, text in samples.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    bundle = tmp_path / "kb"
    result = index_codebase(
        repo,
        bundle,
        languages=[
            "python",
            "javascript",
            "typescript",
            "java",
            "scala",
            "rust",
            "go",
            "kotlin",
            "perl",
            "csharp",
            "php",
            "html",
        ],
    )

    assert result.written == len(samples)
    assert validate_bundle(bundle).conformant
    index = build_index(bundle)
    for term in (
        "PyService",
        "JsService",
        "TsService",
        "Card",
        "JavaService",
        "ScalaService",
        "RustService",
        "GoService",
        "KotlinService",
        "PerlService",
        "CSharpService",
        "PhpService",
        "main",
    ):
        assert search(index, term), term
