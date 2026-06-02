"""分析测试场景矩阵：多提示词 + 预期回复。

维护原则（与 .cursor/rules/analysis-testing-coverage.mdc 一致）：
- 每个 analysis_type 至少 1 条场景
- 每种 chart_type 至少 1 条可渲染样本
- 同一意图用 2+ 种用户说法（queries 列表）
- 改路由/修复逻辑后跑 test_analysis_coverage 收敛
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ScenarioTier = Literal["deterministic", "llm"]


@dataclass(frozen=True)
class Expectation:
    """对 analyze 或 repair 链路的结构化预期。"""

    analysis_type: str | None = None
    chart_type: str | None = None
    chart_type_in: tuple[str, ...] = ()
    mode: str | None = None
    mode_in: tuple[str, ...] = ()
    matched_event: str | None = None
    matched_event_contains: str | None = None
    dimension: str | None = None
    min_filtered_rows: int = 1
    min_panel_count: int = 0
    min_chart_points: int = 1
    csv_event_filter: list[str] | None = None
    csv_event_filter_excludes: tuple[str, ...] = ()
    no_comparison_events: bool = False
    scope_mode: str | None = None


@dataclass(frozen=True)
class QueryScenario:
    """同一意图的多种用户说法 + 预期。"""

    id: str
    queries: tuple[str, ...]
    tier: ScenarioTier
    expect: Expectation
    mock_llm_payload: dict[str, Any] | None = None
    repair_pipeline: tuple[str, ...] = ("repair_plan_llm_payload",)
    notes: str = ""


# --- 路由 / 修复（不调用 LLM，用 mock payload + repair 链收敛）---

REPAIR_SCENARIOS: tuple[QueryScenario, ...] = (
    QueryScenario(
        id="usage_retention_not_funnel",
        queries=(
            "进入carlog1次和2次的用户数",
            "carlog使用1次和2次的车辆数",
            "我想看进入carlog1次和2次有多少车",
        ),
        tier="deterministic",
        expect=Expectation(
            analysis_type="usage_retention",
            chart_type="bar",
            dimension="使用次数分组",
            csv_event_filter=["carlog_entry"],
            no_comparison_events=True,
        ),
        mock_llm_payload={
            "analysis_type": "funnel",
            "matched_event": "Carlog_进入",
            "matched_module": "Carlog",
            "match_confidence": "high",
            "csv_event_filter": [
                "carlog_entry",
                "carlog_record",
                "carlog_autocut",
                "carlog_exit",
            ],
            "comparison_events": ["Carlog_进入", "Carlog_录制", "Carlog_退出"],
            "metrics": [
                {"id": "user_count", "name": "到达车辆数", "type": "count"},
                {"id": "conversion_rate", "name": "步间转化率(%)", "type": "count"},
            ],
            "visualization": {
                "chart_type": "funnel_chart",
                "layout": "single",
                "reasoning": "漏斗",
            },
            "dimension": "漏斗步骤",
            "filters": {},
            "time_range": {"type": "last_n_days", "value": 30},
            "statistical_caliber": {
                "dedup_method": "按VIN去重",
                "time_granularity": "daily",
                "description": "carlog漏斗",
            },
        },
        notes="LLM 误判漏斗时，repair 应收敛到 usage_retention + 单事件 filter",
    ),
    QueryScenario(
        id="funnel_from_comparison_table",
        queries=(
            "看看carlog漏斗",
            "carlog转化漏斗",
            "Carlog从进入到退出的转化",
        ),
        tier="deterministic",
        expect=Expectation(
            analysis_type="funnel",
            chart_type="funnel_chart",
            min_filtered_rows=0,
        ),
        mock_llm_payload={
            "analysis_type": "event_comparison",
            "matched_event": "Carlog_进入",
            "matched_module": "Carlog",
            "match_confidence": "high",
            "csv_event_filter": ["carlog_entry", "carlog_record", "carlog_exit"],
            "metrics": [
                {"id": "pv", "name": "触发次数", "type": "count"},
                {"id": "uv", "name": "按车去重", "type": "nunique", "field": "vin_code"},
            ],
            "visualization": {
                "chart_type": "table",
                "layout": "single",
                "reasoning": "各事件对比",
            },
            "dimension": "event",
            "filters": {},
            "time_range": {"type": "last_n_days", "value": 30},
            "statistical_caliber": {
                "dedup_method": "按VIN去重",
                "time_granularity": "daily",
                "description": "漏斗",
            },
        },
        repair_pipeline=("repair_funnel_analysis_plan",),
        notes="漏斗意图应覆盖 table 型 event_comparison",
    ),
    QueryScenario(
        id="comprehensive_scope_gate",
        queries=(
            "综合分析一下carlog",
            "全面分析 Carlog 模块",
            "carlog 整体 overview",
        ),
        tier="deterministic",
        expect=Expectation(scope_mode="comprehensive"),
        notes="仅检查 scope 推断，不跑 analyze",
    ),
    QueryScenario(
        id="single_event_no_auto_expand",
        queries=(
            "分析carlog",
            "看看 carlog 数据",
        ),
        tier="deterministic",
        expect=Expectation(scope_mode="single_event"),
        notes="无综合/全面关键词时不应自动 comprehensive",
    ),
)

# --- LLM 端到端（需 DEEPSEEK_API_KEY）---

LLM_SCENARIOS: tuple[QueryScenario, ...] = (
    QueryScenario(
        id="carlog_time_series",
        queries=(
            "Carlog进入最近7天每日趋势",
            "carlog 最近一周 PV 走势",
        ),
        tier="llm",
        expect=Expectation(
            mode="single",
            analysis_type="time_series",
            chart_type_in=("line", "area", "multi_line", "bar"),
            matched_event="Carlog_进入",
            min_filtered_rows=100,
        ),
    ),
    QueryScenario(
        id="carlog_usage_retention",
        queries=(
            "carlog使用1次和2次的车辆数",
            "进入carlog1次和2次的用户数",
        ),
        tier="llm",
        expect=Expectation(
            mode="single",
            analysis_type="usage_retention",
            chart_type_in=("bar", "horizontal_bar", "pie", "table"),
            matched_event="Carlog_进入",
            min_chart_points=1,
        ),
    ),
    QueryScenario(
        id="carlog_funnel",
        queries=(
            "看看carlog漏斗",
            "carlog 转化漏斗分析",
        ),
        tier="llm",
        expect=Expectation(
            mode="single",
            analysis_type="funnel",
            chart_type_in=("funnel_chart", "horizontal_bar", "bar"),
            min_chart_points=2,
        ),
    ),
    QueryScenario(
        id="carlog_comprehensive",
        queries=(
            "全面分析一下carlog",
            "综合分析一下 carlog 模块",
        ),
        tier="llm",
        expect=Expectation(
            mode_in=("comprehensive", "exploratory"),
            min_panel_count=2,
            min_filtered_rows=100,
        ),
    ),
    QueryScenario(
        id="carlog_period_pattern",
        queries=(
            "Carlog各时段触发分布",
            "carlog 按小时的使用高峰",
        ),
        tier="llm",
        expect=Expectation(
            mode="single",
            analysis_type="period_pattern",
            chart_type_in=("bar", "line", "horizontal_bar"),
            min_chart_points=1,
        ),
    ),
    QueryScenario(
        id="carlog_summary_kpi",
        queries=(
            "Carlog进入总共多少次、多少辆车",
            "carlog 总体 PV UV",
        ),
        tier="llm",
        expect=Expectation(
            mode="single",
            analysis_type="summary_kpi",
            chart_type_in=("table", "gauge", "bar", "pie"),
        ),
    ),
    QueryScenario(
        id="carlog_event_comparison",
        queries=(
            "Carlog进入与Carlog退出每日对比",
            "对比 carlog 进入和退出",
        ),
        tier="llm",
        expect=Expectation(
            mode="single",
            analysis_type="event_comparison",
            chart_type_in=("multi_line", "line", "bar", "stacked_bar"),
            min_chart_points=1,
        ),
    ),
    QueryScenario(
        id="nav_comprehensive",
        queries=(
            "综合分析一下导航",
            "全面看看导航模块",
        ),
        tier="llm",
        expect=Expectation(
            mode="comprehensive",
            min_panel_count=2,
            min_filtered_rows=50,
        ),
    ),
)

ALL_QUERY_SCENARIOS: tuple[QueryScenario, ...] = REPAIR_SCENARIOS + LLM_SCENARIOS
