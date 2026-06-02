#!/usr/bin/env python3
"""打印分析覆盖 + 性能矩阵摘要，并跑 deterministic 收敛测试。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.analysis_registry import ANALYSIS_CATALOG, CHART_TYPE_CATALOG  # noqa: E402
from tests.fixtures.analysis_scenarios import ALL_QUERY_SCENARIOS, LLM_SCENARIOS  # noqa: E402
from tests.fixtures.performance_budgets import load_budgets  # noqa: E402
from tests.fixtures.performance_scenarios import LLM_PERF_SCENARIOS, PERF_SCENARIOS  # noqa: E402


def _run_pytest(target: str, extra_args: list[str] | None = None) -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target,
        "-k",
        "not llm",
        "-q",
        "--tb=line",
        *(extra_args or []),
    ]
    return subprocess.run(cmd, cwd=BACKEND).returncode


def main() -> int:
    budgets = load_budgets()
    print("=== Analysis Coverage + Performance Matrix ===\n")
    print(f"analysis_types: {len(ANALYSIS_CATALOG)}")
    print(f"chart_types:    {len(CHART_TYPE_CATALOG)}")
    print(f"query_scenarios: {len(ALL_QUERY_SCENARIOS)} (llm: {len(LLM_SCENARIOS)})")
    print(f"perf_scenarios:  {len(PERF_SCENARIOS)} (llm: {len(LLM_PERF_SCENARIOS)})\n")

    print("--- Performance budgets (ms, after ANALYSIS_PERF_FACTOR) ---")
    for field, value in budgets.__dict__.items():
        print(f"  {field}: {value}")

    print("\n--- Query scenarios ---")
    for s in ALL_QUERY_SCENARIOS:
        q_preview = " | ".join(q[:24] for q in s.queries[:2])
        print(f"  [{s.tier:12}] {s.id:30} {q_preview}")

    print("\n--- Perf scenarios ---")
    for s in PERF_SCENARIOS:
        warm = f" warm<={s.warm_max_wall_ms}ms" if s.warm_max_wall_ms else ""
        print(f"  [{s.tier:12}] {s.id:30} cold<={s.max_wall_ms}ms{warm}")

    print("\n--- Running functional coverage (no llm) ---")
    rc_cov = _run_pytest("tests/test_analysis_coverage.py")
    if rc_cov != 0:
        return rc_cov

    print("\n--- Running performance tests (no llm) ---")
    rc_perf = _run_pytest("tests/test_analysis_performance.py")
    return rc_perf


if __name__ == "__main__":
    raise SystemExit(main())
