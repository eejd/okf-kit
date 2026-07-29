#!/usr/bin/env python3
"""Offline reducer for okf-mcp's structured tool-call logs (Phase 1 of the
instrumentation-before-splitting plan — see ``mcp._log_tool_call``).

Reads newline-delimited JSON tool-call records from stdin (or a file path
argument) and prints a summary covering exactly the signals the plan needs to
decide *whether* and *how* a bundle should eventually be split:

- zero-result rate and score distribution for ``search`` (is the KB able to
  say "I don't know"? — this is the signal for D2/the retrieval floor)
- read-concept traffic by top-level directory (the split signal — if reads
  cluster hard by directory with little cross-directory traversal, that is
  evidence for a domain split; if they don't, that is evidence against one)
- per-tool latency and error rate

Usage:
    docker logs mcp-okf-hive-dev 2>&1 | python3 scripts/analyze_tool_logs.py
    python3 scripts/analyze_tool_logs.py path/to/logfile

Stdlib only, no third-party deps, matching this codebase's ``okf_kit.core``
convention. Malformed lines (anything not starting with the log's own JSON
shape, e.g. interleaved non-JSON container/proxy noise) are silently skipped
— this is a best-effort offline analysis tool, not a validator.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _parse_records(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "tool" in record and "ts" in record:
            records.append(record)
    return records


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def _top_level_dir(concept_id: str) -> str:
    return concept_id.split("/", 1)[0] if "/" in concept_id else "(root)"


def summarize(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    if not records:
        return "no tool-call records found"

    by_tool = Counter(r["tool"] for r in records)
    lines.append(f"Total tool calls: {len(records)}")
    for tool, count in by_tool.most_common():
        lines.append(f"  {tool}: {count}")

    lines.append("")
    lines.append("Per-tool latency (ms) and error rate:")
    for tool in sorted(by_tool):
        tool_records = [r for r in records if r["tool"] == tool]
        latencies = [r["latency_ms"] for r in tool_records if "latency_ms" in r]
        errors = sum(1 for r in tool_records if r.get("ok") is False)
        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        lines.append(
            f"  {tool}: p50={p50:.1f}ms p95={p95:.1f}ms "
            f"errors={errors}/{len(tool_records)}"
        )

    search_records = [r for r in records if r["tool"] == "search"]
    if search_records:
        lines.append("")
        lines.append(f"search: {len(search_records)} calls")
        zero_result = [r for r in search_records if r.get("n_results", 0) == 0]
        lines.append(
            f"  zero-result rate: {len(zero_result)}/{len(search_records)} "
            f"({100 * len(zero_result) / len(search_records):.1f}%)"
        )
        scored = [r["top_score"] for r in search_records if r.get("top_score") is not None]
        if scored:
            lines.append(
                f"  top_score (calls with hits): "
                f"min={min(scored):.1f} p50={_percentile(scored, 50):.1f} max={max(scored):.1f}"
            )
            lines.append(
                "  NOTE: no fixed score threshold is meaningful across queries — "
                "compare distributions over time, don't gate on an absolute number "
                "(scores are unnormalized weighted-TF-with-IDF, not probabilities)."
            )

    read_records = [r for r in records if r["tool"] == "read_concept"]
    if read_records:
        lines.append("")
        lines.append(f"read_concept: {len(read_records)} calls")
        by_dir = Counter(
            _top_level_dir(r["concept_id"]) for r in read_records if r.get("concept_id")
        )
        lines.append("  reads by top-level directory (the split-decision signal):")
        for dirname, count in by_dir.most_common():
            pct = 100 * count / len(read_records)
            lines.append(f"    {dirname}: {count} ({pct:.1f}%)")
        lines.append(
            "  Interpretation: if one or two directories dominate reads with little "
            "cross-directory traversal, that is evidence for a domain split. Even "
            "distribution across many directories is evidence against splitting yet."
        )

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if argv:
        path = Path(argv[0])
        if not path.is_file():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 2
        with path.open(encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    records = _parse_records(lines)
    print(summarize(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
