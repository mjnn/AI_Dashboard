"""多事件综合看板 — 基于相关事件范围批量生成对比与趋势面板。"""

from __future__ import annotations

import time
from typing import List, Optional, Set

import pandas as pd

from schemas.analysis import (
    AnalysisPanel,
    AnalysisResponse,
    AnalysisPlan,
    ExecutionSummary,
    MetricDef,
    VisualizationDef,
)
from services.analysis_registry import (
    EVENT_NAME_DIMENSION,
    normalize_plan_for_analysis,
    wants_funnel_analysis,
)
from services.chart_builder import build
from services.csv_processor import process_csv
from services.dashboard_narrator import (
    apply_presentation_to_panels,
    generate_dashboard_presentation,
)
from services.event_cluster_discovery import (
    EventClusterDiscovery,
    apply_cluster_to_plan,
    discovery_scope_label,
    get_primary_cluster,
)
from services.exploratory_analyzer import (
    build_exploratory_reason,
    detect_feasible_analysis_types,
    run_exploratory_analysis,
    should_run_exploratory,
)


def enrich_plan_for_multi_event(
    plan: AnalysisPlan,
    *,
    discovery: EventClusterDiscovery,
) -> AnalysisPlan:
    """将 LLM 主聚类写入分析计划。"""
    cluster = get_primary_cluster(discovery)
    return apply_cluster_to_plan(plan, discovery, cluster)


def build_multi_event_plans(
    seed: AnalysisPlan,
    *,
    funnel_first: bool = False,
    query: str = "",
) -> List[AnalysisPlan]:
    """构建多事件专属子计划（对比 + 分事件趋势 + 可选漏斗）。"""
    base_metrics = [
        MetricDef(id="pv", name="触发次数", type="count"),
        MetricDef(id="uv", name="独立车辆", type="nunique", field="vin_code"),
    ]

    compare_plan = normalize_plan_for_analysis(
        seed.model_copy(
            update={
                "analysis_type": "event_comparison",
                "dimension": EVENT_NAME_DIMENSION,
                "sub_dimension": None,
                "metrics": base_metrics,
                "visualization": VisualizationDef(
                    chart_type="bar",
                    layout="single",
                    reasoning="相关事件触发量与 UV 对比",
                ),
            }
        ),
        query=query,
    )

    trend_plan = normalize_plan_for_analysis(
        seed.model_copy(
            update={
                "analysis_type": "event_comparison",
                "dimension": "date",
                "sub_dimension": EVENT_NAME_DIMENSION,
                "metrics": [MetricDef(id="pv", name="触发次数", type="count")],
                "visualization": VisualizationDef(
                    chart_type="multi_line",
                    layout="single",
                    reasoning="各相关事件随时间的变化趋势",
                ),
            }
        ),
        query=query,
    )

    funnel_plan: AnalysisPlan | None = None
    if seed.comparison_events and len(seed.comparison_events) >= 2:
        funnel_plan = normalize_plan_for_analysis(
            seed.model_copy(
                update={
                    "analysis_type": "funnel",
                    "metrics": [
                        MetricDef(id="user_count", name="到达车辆数", type="count"),
                        MetricDef(id="conversion_rate", name="步间转化率(%)", type="count"),
                    ],
                    "visualization": VisualizationDef(
                        chart_type="funnel_chart",
                        layout="single",
                        reasoning="相关事件转化漏斗",
                    ),
                }
            ),
            query=query,
        )

    if funnel_plan and funnel_first:
        return [funnel_plan, compare_plan, trend_plan]
    if funnel_plan:
        return [compare_plan, trend_plan, funnel_plan]
    return [compare_plan, trend_plan]


def _run_panel_plans(
    plans: List[AnalysisPlan],
    *,
    event_def: dict,
    df: pd.DataFrame,
    events_index: dict,
    event_filter_override: Set[str],
    id_prefix: str,
) -> tuple[List[AnalysisPanel], Set[str], int, int, bool]:
    panels: List[AnalysisPanel] = []
    all_unavailable: Set[str] = set()
    total_rows = 0
    max_filtered = 0
    any_success = False

    for index, sub_plan in enumerate(plans):
        try:
            data_df, execution = process_csv(
                sub_plan,
                event_def,
                df=df,
                event_filter_override=event_filter_override,
                events_index=events_index,
            )
            records = (
                data_df.to_dict(orient="records") if not data_df.empty else []
            )
            chart_config = build(sub_plan, records)
        except Exception:
            continue

        if execution.total_rows and total_rows == 0:
            total_rows = execution.total_rows
        max_filtered = max(max_filtered, execution.filtered_rows)
        all_unavailable.update(execution.unavailable_dimensions)

        if execution.status == "failed" or not records:
            continue

        any_success = True
        analysis_type = sub_plan.analysis_type or "unknown"
        panel_id = f"{id_prefix}-{analysis_type}-{index}"
        layout = "wide" if analysis_type == "event_comparison" and sub_plan.sub_dimension else "half"

        panels.append(
            AnalysisPanel(
                panel_id=panel_id,
                analysis_type=analysis_type,
                name=chart_config.title,
                layout=layout,
                plan=sub_plan,
                execution=execution,
                chart_config=chart_config,
            )
        )

    return panels, all_unavailable, total_rows, max_filtered, any_success


def run_comprehensive_analysis(
    plan: AnalysisPlan,
    event_def: dict,
    df: pd.DataFrame,
    columns: List[str],
    *,
    query: str,
    user_mode: str,
    events_index: dict,
    csv_event_names: List[str],
    event_filter_override: Set[str],
    cluster_discovery: EventClusterDiscovery,
    locale: str | None = None,
) -> AnalysisResponse:
    """多事件综合看板：LLM 聚类驱动对比面板 + 探索性或精准主分析。"""
    start_ms = time.perf_counter()
    plan = enrich_plan_for_multi_event(plan, discovery=cluster_discovery)
    primary_cluster = get_primary_cluster(cluster_discovery)

    multi_plans = build_multi_event_plans(
        plan,
        funnel_first=wants_funnel_analysis(query),
        query=query,
    )
    multi_panels, multi_unavail, total_rows, max_filtered, multi_ok = _run_panel_plans(
        multi_plans,
        event_def=event_def,
        df=df,
        events_index=events_index,
        event_filter_override=event_filter_override,
        id_prefix="multi",
    )

    core_panels: List[AnalysisPanel] = []
    core_unavail: Set[str] = set()
    core_plan = plan
    exploratory_reason: Optional[str] = None
    mode = "comprehensive"

    if should_run_exploratory(plan, query, user_mode=user_mode):
        feasible = detect_feasible_analysis_types(columns)
        if len(feasible) >= 2:
            exploratory_reason = build_exploratory_reason(
                plan,
                query,
                user_mode=user_mode,
                feasible_count=len(feasible),
            )
            exploratory = run_exploratory_analysis(
                plan,
                event_def,
                df,
                columns,
                reason=exploratory_reason,
                query=query,
                event_filter_override=event_filter_override,
                events_index=events_index,
                locale=locale,
            )
            core_panels = exploratory.panels or []
            core_plan = exploratory.plan
            core_unavail.update(exploratory.execution.unavailable_dimensions)
            total_rows = total_rows or exploratory.execution.total_rows
            max_filtered = max(max_filtered, exploratory.execution.filtered_rows)
            mode = "comprehensive"
            exploratory_reason = (
                f"场景「{primary_cluster.name}」含 {len(event_filter_override)} 个事件；"
                f"{exploratory_reason}"
            )
    else:
        data_df, execution = process_csv(
            plan,
            event_def,
            df=df,
            event_filter_override=event_filter_override,
            events_index=events_index,
        )
        records = data_df.to_dict(orient="records") if not data_df.empty else []
        chart_config = build(plan, records)
        total_rows = total_rows or execution.total_rows
        max_filtered = max(max_filtered, execution.filtered_rows)
        core_unavail.update(execution.unavailable_dimensions)
        if records:
            core_panels.append(
                AnalysisPanel(
                    panel_id="primary",
                    analysis_type=plan.analysis_type or "unknown",
                    name=chart_config.title,
                    layout="wide",
                    plan=plan,
                    execution=execution,
                    chart_config=chart_config,
                )
            )

    panels = multi_panels + core_panels
    scope_label = discovery_scope_label(cluster_discovery)
    display_plan = core_plan.model_copy(
        update={
            "csv_event_filter": sorted(event_filter_override),
            "scope_label": scope_label,
        }
    )

    elapsed = int((time.perf_counter() - start_ms) * 1000)
    any_success = multi_ok or bool(core_panels)
    presentation = generate_dashboard_presentation(
        panels,
        display_plan,
        query or scope_label,
        scope_event_count=len(event_filter_override),
        depth_insights=cluster_discovery.depth_insights,
        analysis_angles=primary_cluster.analysis_angles,
        locale=locale,
    )
    panels = apply_presentation_to_panels(panels, presentation)

    primary = panels[0] if panels else None
    fallback_chart = build(plan, [])

    return AnalysisResponse(
        mode=mode,
        plan=display_plan,
        execution=ExecutionSummary(
            status="success" if any_success else "partial",
            unavailable_dimensions=sorted(multi_unavail | core_unavail),
            total_rows=total_rows,
            filtered_rows=max_filtered,
            execution_time_ms=elapsed,
        ),
        chart_config=primary.chart_config if primary else fallback_chart,
        panels=panels,
        exploratory_reason=exploratory_reason,
        panel_count=len(panels),
        presentation=presentation,
        scope_events=sorted(event_filter_override),
        analysis_clusters=[
            {
                "id": c.id,
                "name": c.name,
                "rationale": c.rationale,
                "csv_events": c.csv_events,
                "analysis_angles": c.analysis_angles,
                "is_primary": c.id == cluster_discovery.primary_cluster_id,
            }
            for c in cluster_discovery.clusters
        ],
        depth_insights=cluster_discovery.depth_insights,
    )
