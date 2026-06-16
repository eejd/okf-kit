"""OKF v0.1 conformance validation (SPEC §9; REQ-BM-04, REQ-API-01..04).

Walks a bundle, classifies every ``.md`` into errors / warnings / info, and
returns a :class:`Report`. The validator is the *only* judge — the parser is
permissive and never raises; this module turns parse diagnostics into
conformance findings.

Severity policy:
- **errors** (block conformance): missing/unparseable frontmatter, empty
  ``type``, malformed reserved files.
- **warnings**: missing recommended fields (``title``/``description``), broken
  internal links.
- **info**: extension frontmatter keys, nested ``index.md`` carrying
  frontmatter (a forward-compat sub-bundle marker — NOT an error), missing or
  mismatched ``okf_version``, empty bundles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from okf_kit.core.links import broken_links, cid_segments_valid, iter_concept_files
from okf_kit.core.parse import parse_concept

_KNOWN_FRONTMATTER_KEYS = frozenset(
    {"type", "title", "description", "resource", "tags", "timestamp", "okf_version"}
)
# Warn only on the human-facing recommended fields; resource/tags/timestamp are
# intentionally optional (often legitimately absent) and stay silent.
_RECOMMENDED_WARN_FIELDS = ("title", "description")
_SUPPORTED_OKF_VERSION = "0.1"


@dataclass
class Finding:
    severity: str  # 'error' | 'warning' | 'info'
    code: str
    message: str
    cid: str | None = None
    path: Path | None = None


@dataclass
class Report:
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    info: list[Finding] = field(default_factory=list)

    @property
    def conformant(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "conformant": self.conformant,
            "errors": [vars(f) for f in self.errors],
            "warnings": [vars(f) for f in self.warnings],
            "info": [vars(f) for f in self.info],
        }


def validate_bundle(root: Path) -> Report:
    """Validate every ``.md`` under ``root`` against OKF v0.1 conformance."""
    root = Path(root).resolve()
    report = Report()
    concept_count = 0
    root_okf_version: str | None = None
    root_index_seen = False

    for md in iter_concept_files(root):
        concept = parse_concept(md, root)
        rel = md.relative_to(root).as_posix()

        if concept.reserved == "index":
            if rel == "index.md":
                root_index_seen = True
                root_okf_version = concept.frontmatter.get("okf_version")
                for key in concept.frontmatter:
                    if key != "okf_version":
                        report.info.append(
                            Finding("info", "index-extra-key",
                                    f"root index.md has unexpected frontmatter key '{key}'",
                                    None, md)
                        )
            elif concept.frontmatter:
                # Forward-compat: a nested index.md carrying frontmatter is the
                # likely sub-bundle marker — info, not error (design §14).
                report.info.append(
                    Finding("info", "nested-index-frontmatter",
                            "nested index.md carries frontmatter (possible sub-bundle marker)",
                            concept.cid, md)
                )
            if concept.frontmatter_error:
                report.errors.append(
                    Finding("error", "frontmatter-invalid", concept.frontmatter_error,
                            concept.cid, md)
                )
            continue

        if concept.reserved == "log":
            if concept.frontmatter_error:
                report.errors.append(
                    Finding("error", "frontmatter-invalid", concept.frontmatter_error,
                            concept.cid, md)
                )
            elif concept.frontmatter:
                report.info.append(
                    Finding("info", "log-frontmatter", "log.md carries frontmatter",
                            concept.cid, md)
                )
            continue

        concept_count += 1
        _check_concept(report, concept)

    if concept_count == 0:
        report.info.append(Finding("info", "empty-bundle", "bundle has no concept files"))

    _check_okf_version(report, root, root_index_seen, root_okf_version)
    return report


def _check_concept(report: Report, concept: Any) -> None:
    if concept.frontmatter_error:
        report.errors.append(
            Finding("error", "frontmatter-invalid", concept.frontmatter_error,
                    concept.cid, concept.path)
        )
        return
    if not concept.frontmatter_present:
        report.errors.append(
            Finding("error", "frontmatter-missing", "missing frontmatter block",
                    concept.cid, concept.path)
        )
        return

    if not cid_segments_valid(concept.cid):
        report.warnings.append(
            Finding(
                "warning",
                "invalid-cid",
                f"concept id '{concept.cid}' violates the SPEC §2.2 segment regex "
                "(unaddressable by read_concept / search-graph)",
                concept.cid,
                concept.path,
            )
        )

    type_value = concept.frontmatter.get("type")
    if not isinstance(type_value, str) or not type_value.strip():
        report.errors.append(
            Finding("error", "type-empty", "frontmatter missing non-empty 'type'",
                    concept.cid, concept.path)
        )

    for name in _RECOMMENDED_WARN_FIELDS:
        value = concept.frontmatter.get(name)
        if value in (None, ""):
            report.warnings.append(
                Finding("warning", f"missing-{name}",
                        f"missing recommended field '{name}'", concept.cid, concept.path)
            )

    for key in concept.frontmatter:
        if key not in _KNOWN_FRONTMATTER_KEYS:
            report.info.append(
                Finding("info", "extension-key", f"extension frontmatter key '{key}'",
                        concept.cid, concept.path)
            )

    for target in broken_links(concept.root, concept):
        report.warnings.append(
            Finding("warning", "broken-link", f"broken internal link '{target}'",
                    concept.cid, concept.path)
        )


def _check_okf_version(
    report: Report, root: Path, root_index_seen: bool, version: str | None
) -> None:
    if not root_index_seen or version is None:
        report.info.append(
            Finding("info", "okf-version-missing",
                    "root index.md missing okf_version", None, root / "index.md")
        )
    elif version != _SUPPORTED_OKF_VERSION:
        report.info.append(
            Finding("info", "okf-version-mismatch",
                    f"okf_version '{version}' (supported: {_SUPPORTED_OKF_VERSION})",
                    None, root / "index.md")
        )
