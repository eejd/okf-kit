"""Managed generated-section merging for code concepts."""
from __future__ import annotations

from okf_kit.core.parse import split_frontmatter

MANAGED_START = "<!-- okf-code:start -->"
MANAGED_END = "<!-- okf-code:end -->"


def merge_managed(existing: str, generated: str) -> str:
    generated_result = split_generated(generated)
    if generated_result is None:
        raise ValueError("generated concept is missing okf-code markers")

    existing_result = split_generated(existing)
    if existing_result is None:
        return generated

    generated_prefix, generated_body, _generated_suffix = generated_result
    existing_prefix, _existing_body, existing_suffix = existing_result
    existing_preface = split_frontmatter(existing_prefix).body
    if existing_preface and not existing_preface.endswith("\n"):
        existing_preface += "\n"
    return generated_prefix + existing_preface + generated_body + existing_suffix


def split_generated(text: str) -> tuple[str, str, str] | None:
    start = text.find(MANAGED_START)
    end = text.find(MANAGED_END)
    if start < 0 or end < start:
        return None
    end += len(MANAGED_END)
    return text[:start], text[start:end] + "\n", text[end:].lstrip("\n")
