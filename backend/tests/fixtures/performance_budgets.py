"""分析链路性能预算（毫秒）。可通过环境变量覆盖或整体放宽。

环境变量：
  ANALYSIS_PERF_FACTOR=1.5          全局乘数（慢机器 / CI）
  ANALYSIS_PERF_<NAME>_MS=3000      单项覆盖，如 ANALYSIS_PERF_DATA_POOL_COLD_MS
  ANALYSIS_PERF_LLM=1|0             是否跑 LLM 端到端性能（默认 1，有 API Key 时）
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _factor() -> float:
    raw = os.getenv("ANALYSIS_PERF_FACTOR", "1.0").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 1.0


def budget_ms(name: str, default: int) -> int:
    """读取单项预算（已乘 ANALYSIS_PERF_FACTOR）。"""
    env_key = f"ANALYSIS_PERF_{name.upper()}_MS"
    raw = os.getenv(env_key, str(default))
    try:
        base = int(raw)
    except ValueError:
        base = default
    return int(base * _factor())


def perf_llm_enabled() -> bool:
    return os.getenv("ANALYSIS_PERF_LLM", "1").lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class PerfBudgets:
    data_pool_cold_ms: int
    data_pool_cached_ms: int
    data_pool_cache_speedup_min: float
    process_csv_type_ms: int
    process_csv_all_types_ms: int
    comprehensive_pipeline_ms: int
    analyze_single_llm_ms: int
    analyze_comprehensive_llm_ms: int
    analyze_comprehensive_warm_ms: int
    analyze_usage_retention_llm_ms: int


def load_budgets() -> PerfBudgets:
    return PerfBudgets(
        data_pool_cold_ms=budget_ms("data_pool_cold", 5000),
        data_pool_cached_ms=budget_ms("data_pool_cached", 100),
        data_pool_cache_speedup_min=float(os.getenv("ANALYSIS_PERF_CACHE_SPEEDUP_MIN", "5")),
        process_csv_type_ms=budget_ms("process_csv_type", 8000),
        process_csv_all_types_ms=budget_ms("process_csv_all_types", 90000),
        comprehensive_pipeline_ms=budget_ms("comprehensive_pipeline", 35000),
        analyze_single_llm_ms=budget_ms("analyze_single_llm", 90000),
        analyze_comprehensive_llm_ms=budget_ms("analyze_comprehensive_llm", 150000),
        analyze_comprehensive_warm_ms=budget_ms("analyze_comprehensive_warm", 60000),
        analyze_usage_retention_llm_ms=budget_ms("analyze_usage_retention_llm", 90000),
    )
