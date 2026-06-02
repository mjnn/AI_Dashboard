"""探索性全量分析 — LLM 意图不明确时，对当前 CSV 可执行的分析类型批量运行。"""

from __future__ import annotations

import json
import re
import time
from typing import List, Literal, Optional, Set

import pandas as pd

from schemas.analysis import (
    AnalysisPanel,
    AnalysisPlan,
    AnalysisResponse,
    ExecutionSummary,
    MetricDef,
    StatisticalCaliber,
    TimeRange,
    VisualizationDef,
)
from services.analysis_registry import (
    ANALYSIS_SPEC_BY_ID,
    SUMMARY_DIMENSION,
    get_analysis_spec,
    normalize_plan_for_analysis,
)
from services.chart_builder import build
from services.csv_processor import process_csv
from services.dashboard_narrator import (
    apply_presentation_to_panels,
    generate_dashboard_presentation,
)

LayoutHint = Literal["kpi", "wide", "half", "compact"]

_TIME_COL_PATTERN = re.compile(r"date|time|timestamp|日期|时间", re.I)
_EVENT_COL_PATTERN = re.compile(r"event|事件", re.I)
_VIN_COL_PATTERN = re.compile(r"vin", re.I)
_STANDARD_COLS = _TIME_COL_PATTERN, _EVENT_COL_PATTERN, _VIN_COL_PATTERN

_VAGUE_QUERY_PATTERN = re.compile(
    r"^(帮我)?(分析|看看|了解一下|概况|整体|全面|综合|概览|情况怎么样|什么情况)"
    r"|分析一下$|全面分析$|整体分析$",
    re.I,
)

# 探索模式执行顺序（KPI → 趋势 → 行为 → 规律）
EXPLORATORY_TYPE_ORDER: list[str] = [
    "summary_kpi",
    "active_users",
    "stickiness",
    "repeat_rate",
    "time_series",
    "first_touch_trend",
    "growth_rate",
    "usage_retention",
    "usage_distribution",
    "new_vs_returning",
    "active_days_distribution",
    "period_pattern",
    "percentile_stats",
    "heatmap_time",
    "cohort_retention",
    "dimension_breakdown",
    "top_n_ranking",
]

LAYOUT_BY_TYPE: dict[str, LayoutHint] = {
    "summary_kpi": "kpi",
    "active_users": "kpi",
    "stickiness": "kpi",
    "repeat_rate": "kpi",
    "time_series": "wide",
    "first_touch_trend": "wide",
    "growth_rate": "wide",
    "cohort_retention": "wide",
    "heatmap_time": "wide",
    "usage_retention": "half",
    "usage_distribution": "half",
    "new_vs_returning": "half",
    "active_days_distribution": "half",
    "period_pattern": "half",
    "percentile_stats": "half",
    "dimension_breakdown": "half",
    "top_n_ranking": "half",
}


def _is_standard_column(col: str) -> bool:
    return any(p.search(col) for p in _STANDARD_COLS)


def detect_feasible_analysis_types(columns: List[str]) -> Set[str]:
    """根据 CSV 列结构判断可执行的分析类型。"""
    has_time = any(_TIME_COL_PATTERN.search(c) for c in columns)
    has_event = any(_EVENT_COL_PATTERN.search(c) for c in columns)
    has_vin = any(_VIN_COL_PATTERN.search(c) for c in columns)

    feasible: Set[str] = set()
    if has_event and has_time and has_vin:
        feasible.update(
            {
                "time_series",
                "summary_kpi",
                "usage_retention",
                "usage_distribution",
                "active_days_distribution",
                "period_pattern",
                "new_vs_returning",
                "repeat_rate",
                "cohort_retention",
                "active_users",
                "growth_rate",
                "stickiness",
                "percentile_stats",
                "heatmap_time",
                "first_touch_trend",
            }
        )

    extra_dims = [c for c in columns if not _is_standard_column(c)]
    if extra_dims:
        feasible.add("dimension_breakdown")
        feasible.add("top_n_ranking")

    return feasible


def should_run_exploratory(
    plan: AnalysisPlan,
    query: str,
    *,
    user_mode: str = "auto",
) -> bool:
    """判断是否需要进入探索性全量分析模式。"""
    if user_mode == "precise":
        return False
    if user_mode == "exploratory":
        return True

    # auto：沿用原有启发式
    if plan.exploratory_mode:
        return True
    if plan.intent_confidence == "low":
        return True
    if plan.match_confidence == "low":
        return True
    trimmed = query.strip()
    if _VAGUE_QUERY_PATTERN.search(trimmed):
        return True
    if len(trimmed) <= 8 and "分析" in trimmed:
        return True
    return False


def build_exploratory_reason(
    plan: AnalysisPlan,
    query: str,
    *,
    user_mode: str,
    feasible_count: int,
) -> str:
    """组装探索性模式的说明文案。"""
    if user_mode == "exploratory":
        return f"用户手动选择了探索模式，已执行 {feasible_count} 类可行分析"

    reasons: list[str] = []
    if plan.intent_confidence == "low":
        reasons.append("分析意图不明确")
    if plan.match_confidence == "low":
        reasons.append("事件匹配置信度较低")
    if plan.exploratory_mode:
        reasons.append("用户要求全面分析")
    if _VAGUE_QUERY_PATTERN.search(query.strip()):
        reasons.append("问题描述较为笼统")
    if not reasons:
        reasons.append("智能模式判定需全面探索")
    return "；".join(reasons) + f"，已自动执行 {feasible_count} 类可行分析"


def _default_metrics(analysis_type: str) -> List[MetricDef]:
    templates: dict[str, List[MetricDef]] = {
        "time_series": [
            MetricDef(id="pv", name="触发次数", type="count"),
            MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
        ],
        "summary_kpi": [
            MetricDef(id="pv", name="触发次数", type="count"),
            MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
        ],
        "usage_retention": [
            MetricDef(id="vehicle_count", name="车辆数", type="count"),
        ],
        "usage_distribution": [
            MetricDef(id="vehicle_count", name="车辆数", type="count"),
        ],
        "active_days_distribution": [
            MetricDef(id="vehicle_count", name="车辆数", type="count"),
        ],
        "new_vs_returning": [
            MetricDef(id="vehicle_count", name="车辆数", type="count"),
        ],
        "repeat_rate": [
            MetricDef(id="repeat_rate", name="复访率(%)", type="count"),
        ],
        "cohort_retention": [
            MetricDef(id="retention_rate", name="留存率(%)", type="count"),
        ],
        "active_users": [
            MetricDef(id="uv", name="活跃用户", type="nunique", field="vin_code"),
        ],
        "growth_rate": [
            MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
        ],
        "stickiness": [
            MetricDef(id="stickiness", name="粘性(%)", type="count"),
        ],
        "percentile_stats": [
            MetricDef(id="usage_count", name="使用次数", type="count"),
        ],
        "heatmap_time": [
            MetricDef(id="pv", name="触发次数", type="count"),
        ],
        "first_touch_trend": [
            MetricDef(id="new_users", name="新增用户", type="count"),
        ],
        "period_pattern": [
            MetricDef(id="pv", name="触发次数", type="count"),
        ],
        "dimension_breakdown": [
            MetricDef(id="pv", name="触发次数", type="count"),
        ],
        "top_n_ranking": [
            MetricDef(id="pv", name="触发次数", type="count"),
        ],
    }
    return templates.get(
        analysis_type,
        [MetricDef(id="pv", name="触发次数", type="count")],
    )


def _default_visualization(analysis_type: str) -> VisualizationDef:
    spec = get_analysis_spec(analysis_type)
    chart_type = spec["default_chart"] if spec else "bar"
    return VisualizationDef(
        chart_type=chart_type,  # type: ignore[arg-type]
        layout="single",
        reasoning=f"探索性分析默认选用 {chart_type}",
    )


def _default_caliber(seed: AnalysisPlan, analysis_type: str) -> StatisticalCaliber:
    spec = ANALYSIS_SPEC_BY_ID.get(analysis_type)
    if spec:
        description = spec["description"]
    else:
        name = analysis_type
        description = f"探索性分析：{name}（{seed.matched_event}）"
    return StatisticalCaliber(
        dedup_method=seed.statistical_caliber.dedup_method,
        time_granularity=seed.statistical_caliber.time_granularity,
        description=description,
    )


def build_exploratory_plan(
    seed: AnalysisPlan,
    analysis_type: str,
    *,
    breakdown_dimension: Optional[str] = None,
    period_unit: Optional[str] = None,
) -> AnalysisPlan:
    """基于 LLM 种子计划生成单个探索性子计划。"""
    spec = get_analysis_spec(analysis_type)
    dimension = spec["dimension"] if spec else "date"

    updates: dict = {
        "analysis_type": analysis_type,
        "metrics": _default_metrics(analysis_type),
        "statistical_caliber": _default_caliber(seed, analysis_type),
        "visualization": _default_visualization(analysis_type),
        "dimension": dimension,
        "sub_dimension": None,
        "comparison_events": None,
        "top_n": 10 if analysis_type == "top_n_ranking" else None,
        "cohort_retention_days": [1, 7, 14] if analysis_type == "cohort_retention" else None,
        "match_confidence": seed.match_confidence,
        "intent_confidence": seed.intent_confidence,
        "exploratory_mode": False,
    }

    if analysis_type == "dimension_breakdown" and breakdown_dimension:
        updates["dimension"] = breakdown_dimension
    if analysis_type == "top_n_ranking" and breakdown_dimension:
        updates["dimension"] = breakdown_dimension
    if analysis_type == "period_pattern":
        updates["period_unit"] = period_unit or "hour"
    if analysis_type == "period_pattern" and period_unit == "weekday":
        updates["dimension"] = "星期"

    plan = seed.model_copy(update=updates)
    return normalize_plan_for_analysis(plan)


def build_exploratory_plans(
    seed: AnalysisPlan,
    feasible_types: Set[str],
    columns: List[str],
) -> List[AnalysisPlan]:
    """构建当前 CSV 可执行的全部探索性子计划。"""
    extra_dims = [c for c in columns if not _is_standard_column(c)]
    breakdown_dim = extra_dims[0] if extra_dims else None

    plans: List[AnalysisPlan] = []
    for analysis_type in EXPLORATORY_TYPE_ORDER:
        if analysis_type not in feasible_types:
            continue
        if analysis_type in ("dimension_breakdown", "top_n_ranking") and not breakdown_dim:
            continue
        if analysis_type == "period_pattern":
            plans.append(
                build_exploratory_plan(seed, analysis_type, period_unit="hour")
            )
            plans.append(
                build_exploratory_plan(seed, analysis_type, period_unit="weekday")
            )
            continue
        plans.append(
            build_exploratory_plan(
                seed,
                analysis_type,
                breakdown_dimension=breakdown_dim,
            )
        )
    return plans


def _layout_hint(analysis_type: str, period_unit: Optional[str] = None) -> LayoutHint:
    if analysis_type == "period_pattern" and period_unit == "weekday":
        return "half"
    return LAYOUT_BY_TYPE.get(analysis_type, "half")


def _panel_name(plan: AnalysisPlan) -> str:
    spec = get_analysis_spec(plan.analysis_type or "")
    base = spec["name"] if spec else plan.analysis_type or "分析"
    if plan.analysis_type == "period_pattern":
        unit = "按星期" if plan.period_unit == "weekday" else "按小时"
        return f"{base}（{unit}）"
    return base


def run_exploratory_analysis(
    seed_plan: AnalysisPlan,
    event_def: dict,
    df: pd.DataFrame,
    columns: List[str],
    *,
    reason: str,
    query: str = "",
    event_filter_override: Optional[set[str]] = None,
    events_index: dict | None = None,
    locale: str | None = None,
) -> AnalysisResponse:
    """批量执行探索性分析并组装多面板响应。"""
    start_ms = time.perf_counter()
    feasible = detect_feasible_analysis_types(columns)
    sub_plans = build_exploratory_plans(seed_plan, feasible, columns)

    panels: List[AnalysisPanel] = []
    all_unavailable: Set[str] = set()
    total_rows = 0
    max_filtered = 0
    any_success = False

    for index, sub_plan in enumerate(sub_plans):
        analysis_type = sub_plan.analysis_type or "unknown"
        try:
            data_df, execution = process_csv(
                sub_plan,
                event_def,
                df=df,
                event_filter_override=event_filter_override,
                events_index=events_index,
            )
            records = _df_to_records(data_df)
            display_plan = sub_plan
            if event_filter_override:
                display_plan = sub_plan.model_copy(
                    update={"csv_event_filter": sorted(event_filter_override)}
                )
            chart_config = build(
                display_plan,
                records,
                events_index=events_index,
                locale=locale,
            )
        except Exception:
            continue

        if execution.total_rows and total_rows == 0:
            total_rows = execution.total_rows
        max_filtered = max(max_filtered, execution.filtered_rows)
        all_unavailable.update(execution.unavailable_dimensions)

        if execution.status == "failed" or not records:
            continue

        any_success = True
        panel_id = f"{analysis_type}-{index}"
        if sub_plan.period_unit:
            panel_id = f"{analysis_type}-{sub_plan.period_unit}-{index}"

        panels.append(
            AnalysisPanel(
                panel_id=panel_id,
                analysis_type=analysis_type,
                name=_panel_name(sub_plan),
                layout=_layout_hint(analysis_type, sub_plan.period_unit),
                plan=sub_plan,
                execution=execution,
                chart_config=chart_config,
            )
        )

    elapsed = int((time.perf_counter() - start_ms) * 1000)
    aggregate_status = "success" if any_success else "partial"

    presentation = generate_dashboard_presentation(
        panels,
        seed_plan,
        query or seed_plan.matched_event,
        scope_event_count=len(event_filter_override) if event_filter_override else 1,
        locale=locale,
        events_index=events_index,
    )
    panels = apply_presentation_to_panels(panels, presentation)

    primary = panels[0] if panels else None
    fallback_plan = seed_plan
    fallback_chart = build(
        seed_plan,
        [],
    )

    return AnalysisResponse(
        mode="exploratory",
        plan=primary.plan if primary else fallback_plan,
        execution=ExecutionSummary(
            status=aggregate_status,
            unavailable_dimensions=sorted(all_unavailable),
            total_rows=total_rows,
            filtered_rows=max_filtered,
            execution_time_ms=elapsed,
        ),
        chart_config=primary.chart_config if primary else fallback_chart,
        panels=panels,
        exploratory_reason=reason,
        panel_count=len(panels),
        presentation=presentation,
    )


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))
