"""LLM / API 性能场景：多提示词 + 墙钟预算 + 可选暖缓存二次请求。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tests.fixtures.performance_budgets import load_budgets

PerfTier = Literal["deterministic", "llm"]


@dataclass(frozen=True)
class PerfScenario:
    id: str
    queries: tuple[str, ...]
    tier: PerfTier
    max_wall_ms: int
    warm_max_wall_ms: int | None = None
    notes: str = ""


def _b():
    return load_budgets()


# 与 analysis_scenarios 对齐的核心路径；预算取自 performance_budgets（可 env 覆盖）
PERF_SCENARIOS: tuple[PerfScenario, ...] = (
    PerfScenario(
        id="data_pool_warm_hit",
        queries=("load_data_pool",),
        tier="deterministic",
        max_wall_ms=_b().data_pool_cached_ms,
        notes="第二次 load_data_pool 应命中进程内缓存",
    ),
    PerfScenario(
        id="usage_retention_single",
        queries=(
            "carlog使用1次和2次的车辆数",
            "进入carlog1次和2次的用户数",
        ),
        tier="llm",
        max_wall_ms=_b().analyze_usage_retention_llm_ms,
        notes="单事件频次分析",
    ),
    PerfScenario(
        id="comprehensive_carlog_cold",
        queries=(
            "全面分析一下carlog",
            "综合分析一下 carlog 模块",
        ),
        tier="llm",
        max_wall_ms=_b().analyze_comprehensive_llm_ms,
        warm_max_wall_ms=_b().analyze_comprehensive_warm_ms,
        notes="综合分析冷启动 + 路线缓存暖启动",
    ),
    PerfScenario(
        id="comprehensive_nav_cold",
        queries=(
            "综合分析一下导航",
        ),
        tier="llm",
        max_wall_ms=_b().analyze_comprehensive_llm_ms,
        warm_max_wall_ms=_b().analyze_comprehensive_warm_ms,
        notes="多事件 scope 较大的综合看板",
    ),
    PerfScenario(
        id="single_time_series",
        queries=(
            "Carlog进入最近7天每日趋势",
        ),
        tier="llm",
        max_wall_ms=_b().analyze_single_llm_ms,
        notes="单面板时间趋势",
    ),
)

DETERMINISTIC_PERF_SCENARIOS = tuple(s for s in PERF_SCENARIOS if s.tier == "deterministic")
LLM_PERF_SCENARIOS = tuple(s for s in PERF_SCENARIOS if s.tier == "llm")
