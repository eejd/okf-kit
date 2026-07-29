"""Tests for scripts/analyze_tool_logs.py — the Phase-1 offline log reducer."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "analyze_tool_logs.py"
_spec = importlib.util.spec_from_file_location("analyze_tool_logs", SCRIPT_PATH)
assert _spec and _spec.loader
analyze_tool_logs = importlib.util.module_from_spec(_spec)
sys.modules["analyze_tool_logs"] = analyze_tool_logs
_spec.loader.exec_module(analyze_tool_logs)


def test_parse_records_skips_malformed_and_non_log_lines():
    lines = [
        '{"tool": "search", "ts": "2026-07-29T00:00:00+00:00", "ok": true}',
        "not json at all",
        '{"no_tool_or_ts": true}',
        "",
        "   ",
    ]
    records = analyze_tool_logs._parse_records(lines)
    assert len(records) == 1
    assert records[0]["tool"] == "search"


def test_percentile_boundaries():
    assert analyze_tool_logs._percentile([], 50) == 0.0
    assert analyze_tool_logs._percentile([1.0, 2.0, 3.0], 0) == 1.0
    assert analyze_tool_logs._percentile([1.0, 2.0, 3.0], 100) == 3.0


def test_top_level_dir():
    assert analyze_tool_logs._top_level_dir("hives/queen-hive") == "hives"
    assert analyze_tool_logs._top_level_dir("DIALECT") == "(root)"


def test_summarize_zero_result_rate_and_directory_split():
    records = [
        {"tool": "search", "ts": "t", "ok": True, "latency_ms": 10, "n_results": 3, "top_score": 100.0},
        {"tool": "search", "ts": "t", "ok": True, "latency_ms": 5, "n_results": 0},
        {"tool": "read_concept", "ts": "t", "ok": True, "latency_ms": 1, "concept_id": "hives/a"},
        {"tool": "read_concept", "ts": "t", "ok": True, "latency_ms": 1, "concept_id": "hives/b"},
        {"tool": "read_concept", "ts": "t", "ok": False, "latency_ms": 1, "concept_id": "services/c"},
    ]
    summary = analyze_tool_logs.summarize(records)
    assert "zero-result rate: 1/2 (50.0%)" in summary
    assert "hives: 2 (66.7%)" in summary
    assert "services: 1 (33.3%)" in summary
    assert "errors=1/3" in summary  # read_concept: 1 of 3 calls failed


def test_summarize_empty_input():
    assert analyze_tool_logs.summarize([]) == "no tool-call records found"


def test_main_reads_from_file(tmp_path: Path, capsys):
    log_file = tmp_path / "log.jsonl"
    log_file.write_text(
        '{"tool": "search", "ts": "t", "ok": true, "latency_ms": 1, "n_results": 1, "top_score": 5.0}\n',
        encoding="utf-8",
    )
    exit_code = analyze_tool_logs.main([str(log_file)])
    assert exit_code == 0
    assert "Total tool calls: 1" in capsys.readouterr().out


def test_main_missing_file_returns_error_code(tmp_path: Path):
    assert analyze_tool_logs.main([str(tmp_path / "nope.jsonl")]) == 2
