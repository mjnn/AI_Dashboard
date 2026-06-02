"""多事件综合看板 — 基于相关事件范围批量生成对比与趋势面板。"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Set, Tuple

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
    repair_funnel_analysis_plan,
    wants_funnel_analysis,
    wants_usage_frequency_analysis,
)
from services.chart_builder import build
from services.csv_processor import process_csv
from services.event_mapping import infer_csv_filter_for_comparison
from services.field_resolver import resolve_event
from services.event_display import localized_plan_event_title
from services.dashboard_narrator import (
    apply_presentation_to_panels,
    generate_dashboard_presentation,
)
from services.event_cluster_discovery import (
    EventClusterDiscovery,
    apply_cluster_to_plan,
    comparison_steps_from_cluster,
    discovery_scope_label,
    get_primary_cluster,
)
from services.exploratory_analyzer import (
    build_exploratory_reason,
    detect_feasible_analysis_types,
    run_exploratory_analysis,
    should_run_exploratory,
)

MAX_PER_EVENT_PANELS = 12


def _should_include_funnel(query: str, scope: Set[str]) -> bool:
    if wants_usage_frequency_analysis(query):
        return False
    if wants_funnel_analysis(query):
        return True
    return False


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
        MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
    ]

    scope_clear = {"csv_event_filter": None, "comparison_events": None}
    compare_plan = normalize_plan_for_analysis(
        seed.model_copy(
            update={
                **scope_clear,
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
                **scope_clear,
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
                    **scope_clear,
                    "analysis_type": "funnel",
                    "comparison_events": seed.comparison_events,
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


def build_per_event_plans(
    seed: AnalysisPlan,
    scope_events: Set[str],
    *,
    events_index: dict,
    csv_event_names: list[str],
    query: str = "",
) -> Tuple[List[AnalysisPlan], List[Set[str]]]:
    """为范围内每个字典事件生成单独的时间趋势子计划（同一 canonical 只保留一条）。"""
    metrics = [
        MetricDef(id="pv", name="触发次数", type="count"),
        MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
    ]
    plans: List[AnalysisPlan] = []
    scopes: List[Set[str]] = []
    seen_matched: Set[str] = set()
    for csv_event in sorted(scope_events)[:MAX_PER_EVENT_PANELS]:
        try:
            resolved = resolve_event(
                csv_event,
                events_index,
                csv_event_names=csv_event_names,
                query=query,
            )
            matched = resolved.event_name
        except Exception:
            matched = str(csv_event)
        if matched in seen_matched:
            continue
        seen_matched.add(matched)
        plans.append(
            normalize_plan_for_analysis(
                seed.model_copy(
                    update={
                        "matched_event": matched,
                        "matched_module": seed.matched_module,
                        "csv_event_filter": None,
                        "comparison_events": None,
                        "analysis_type": "time_series",
                        "dimension": "date",
                        "sub_dimension": None,
                        "metrics": metrics,
                        "visualization": VisualizationDef(
                            chart_type="line",
                            layout="single",
                            reasoning=f"{matched} 单事件时间趋势",
                        ),
                    }
                ),
                query=query,
            )
        )
        scopes.append({csv_event})
    return plans, scopes


MAX_PER_EVENT_PANELS = 12
_PANEL_WORKERS = max(1, int(os.getenv("ANALYSIS_PANEL_WORKERS", "4")))


def _panel_workers_for(count: int) -> int:
    if count <= 1:
        return 1
    return min(_PANEL_WORKERS, count)


def _build_panel_from_plan(
    index: int,
    sub_plan: AnalysisPlan,
    *,
    scope: Set[str],
    event_def: dict,
    df: pd.DataFrame,
    events_index: dict,
    id_prefix: str,
    locale: str | None,
) -> Tuple[int, Optional[AnalysisPanel], Set[str], int, int, bool]:
    """构建单个面板；供串行/并行调用。"""
    unavailable: Set[str] = set()
    total_rows = 0
    max_filtered = 0
    try:
        data_df, execution = process_csv(
            sub_plan,
            event_def,
            df=df,
            event_filter_override=scope,
            events_index=events_index,
        )
        records = data_df.to_dict(orient="records") if not data_df.empty else []
        display_plan = sub_plan
        if scope:
            display_plan = sub_plan.model_copy(
                update={"csv_event_filter": sorted(scope)}
            )
        chart_config = build(
            display_plan,
            records,
            events_index=events_index,
            locale=locale,
        )
    except Exception:
        return index, None, unavailable, total_rows, max_filtered, False

    total_rows = execution.total_rows or 0
    max_filtered = execution.filtered_rows
    unavailable.update(execution.unavailable_dimensions)

    if execution.status == "failed" or not records:
        return index, None, unavailable, total_rows, max_filtered, False

    analysis_type = sub_plan.analysis_type or "unknown"
    panel_id = f"{id_prefix}-{analysis_type}-{index}"
    if id_prefix == "event":
        panel_id = f"event-{index}-{sub_plan.matched_event}"
        layout = "half"
    elif analysis_type == "event_comparison" and sub_plan.sub_dimension:
        layout = "wide"
    else:
        layout = "half"

    panel = AnalysisPanel(
        panel_id=panel_id,
        analysis_type=analysis_type,
        name=(
            localized_plan_event_title(
                sub_plan,
                events_index,
                locale=locale,
                suffix="日趋势",
            )
            if id_prefix == "event"
            else chart_config.title
        ),
        layout=layout,
        plan=sub_plan,
        execution=execution,
        chart_config=chart_config,
    )
    return index, panel, unavailable, total_rows, max_filtered, True


def _run_panel_plans(
    plans: List[AnalysisPlan],
    *,
    event_def: dict,
    df: pd.DataFrame,
    events_index: dict,
    event_filter_override: Set[str],
    id_prefix: str,
    per_plan_scope: Optional[List[Set[str]]] = None,
    locale: str | None = None,
) -> tuple[List[AnalysisPanel], Set[str], int, int, bool]:
    panels: List[AnalysisPanel] = []
    all_unavailable: Set[str] = set()
    total_rows = 0
    max_filtered = 0
    any_success = False

    if not plans:
        return panels, all_unavailable, total_rows, max_filtered, any_success

    scopes: List[Set[str]] = []
    for index, _ in enumerate(plans):
        scope = event_filter_override
        if per_plan_scope is not None and index < len(per_plan_scope):
            scope = per_plan_scope[index]
        scopes.append(scope)

    results: List[
        Tuple[int, Optional[AnalysisPanel], Set[str], int, int, bool]
    ] = []

    if len(plans) == 1:
        results.append(
            _build_panel_from_plan(
                0,
                plans[0],
                scope=scopes[0],
                event_def=event_def,
                df=df,
                events_index=events_index,
                id_prefix=id_prefix,
                locale=locale,
            )
        )
    else:
        workers = _panel_workers_for(len(plans))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _build_panel_from_plan,
                    index,
                    sub_plan,
                    scope=scopes[index],
                    event_def=event_def,
                    df=df,
                    events_index=events_index,
                    id_prefix=id_prefix,
                    locale=locale,
                )
                for index, sub_plan in enumerate(plans)
            ]
            for future in as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda item: item[0])
    for _index, panel, unavail, rows, filtered, ok in results:
        all_unavailable.update(unavail)
        if rows and total_rows == 0:
            total_rows = rows
        max_filtered = max(max_filtered, filtered)
        if panel is not None:
            panels.append(panel)
            any_success = any_success or ok

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
    scope_size = len(event_filter_override)

    if scope_size >= 2 and not plan.comparison_events:
        steps = comparison_steps_from_cluster(primary_cluster)
        if len(steps) >= 2:
            plan = plan.model_copy(update={"comparison_events": steps})

    funnel_payload = repair_funnel_analysis_plan(
        plan.model_dump(),
        query,
        csv_event_names=csv_event_names,
        events_index=events_index,
    )
    if funnel_payload.get("analysis_type") == "funnel":
        plan = plan.model_copy(
            update={
                "comparison_events": funnel_payload.get("comparison_events")
                or plan.comparison_events,
            }
        )

    multi_plans = build_multi_event_plans(
        plan,
        funnel_first=_should_include_funnel(query, event_filter_override),
        query=query,
    )
    multi_panels, multi_unavail, total_rows, max_filtered, multi_ok = _run_panel_plans(
        multi_plans,
        event_def=event_def,
        df=df,
        events_index=events_index,
        event_filter_override=event_filter_override,
        id_prefix="multi",
        locale=locale,
    )

    per_event_panels: List[AnalysisPanel] = []
    if scope_size >= 2 and not wants_funnel_analysis(query):
        per_plans, per_scopes = build_per_event_plans(
            plan,
            event_filter_override,
            events_index=events_index,
            csv_event_names=csv_event_names,
            query=query,
        )
        per_event_panels, per_unavail, per_rows, per_filtered, per_ok = _run_panel_plans(
            per_plans,
            event_def=event_def,
            df=df,
            events_index=events_index,
            event_filter_override=event_filter_override,
            id_prefix="event",
            per_plan_scope=per_scopes,
            locale=locale,
        )
        multi_unavail |= per_unavail
        total_rows = total_rows or per_rows
        max_filtered = max(max_filtered, per_filtered)
        multi_ok = multi_ok or per_ok

    core_panels: List[AnalysisPanel] = []
    core_unavail: Set[str] = set()
    core_plan = plan
    exploratory_reason: Optional[str] = None
    mode = "comprehensive"

    run_exploratory = should_run_exploratory(
        plan, query, user_mode=user_mode
    ) and scope_size < 2

    if run_exploratory:
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
        skip_core_primary = scope_size >= 2 and bool(multi_panels or per_event_panels)
        if not skip_core_primary:
            data_df, execution = process_csv(
                plan,
                event_def,
                df=df,
                event_filter_override=event_filter_override,
                events_index=events_index,
            )
            records = data_df.to_dict(orient="records") if not data_df.empty else []
            display_plan = plan
            if event_filter_override:
                display_plan = plan.model_copy(
                    update={"csv_event_filter": sorted(event_filter_override)}
                )
            chart_config = build(
                display_plan, records, events_index=events_index, locale=locale
            )
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

    panels = multi_panels + per_event_panels + core_panels
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
        events_index=events_index,
        use_llm=False,
    )
    panels = apply_presentation_to_panels(panels, presentation)

    primary = panels[0] if panels else None
    fallback_chart = build(plan, [], events_index=events_index, locale=locale)

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


def run_funnel_dashboard(
    plan: AnalysisPlan,
    event_def: dict,
    df: pd.DataFrame,
    *,
    query: str,
    events_index: dict,
    csv_event_names: List[str],
    event_filter_override: Set[str] | None,
    locale: str | None = None,
) -> AnalysisResponse:
    """漏斗专项看板：漏斗 + 步骤对比 + 步骤趋势，避免整模块逐事件重复折线。"""
    start_ms = time.perf_counter()
    working = plan
    funnel_payload = repair_funnel_analysis_plan(
        plan.model_dump(),
        query,
        csv_event_names=csv_event_names,
        events_index=events_index,
    )
    comparison = funnel_payload.get("comparison_events") or working.comparison_events
    if comparison:
        working = working.model_copy(update={"comparison_events": comparison})

    scope: Set[str] = set(event_filter_override or [])
    if comparison:
        funnel_scope = infer_csv_filter_for_comparison(
            comparison,
            events_index,
            csv_event_names,
            query=query,
        )
        if funnel_scope:
            scope = set(funnel_scope)

    multi_plans = build_multi_event_plans(working, funnel_first=True, query=query)
    panels, unavail, total_rows, max_filtered, ok = _run_panel_plans(
        multi_plans,
        event_def=event_def,
        df=df,
        events_index=events_index,
        event_filter_override=scope,
        id_prefix="funnel",
        locale=locale,
    )

    display_plan = working.model_copy(
        update={
            "analysis_type": "funnel",
            "csv_event_filter": sorted(scope) if scope else working.csv_event_filter,
        }
    )
    elapsed = int((time.perf_counter() - start_ms) * 1000)
    presentation = generate_dashboard_presentation(
        panels,
        display_plan,
        query,
        scope_event_count=len(scope) if scope else len(comparison or []),
        locale=locale,
        events_index=events_index,
        use_llm=True,
    )
    panels = apply_presentation_to_panels(panels, presentation)
    primary = panels[0] if panels else None
    fallback_chart = build(working, [], events_index=events_index, locale=locale)

    return AnalysisResponse(
        mode="comprehensive",
        plan=display_plan,
        execution=ExecutionSummary(
            status="success" if ok else "partial",
            unavailable_dimensions=sorted(unavail),
            total_rows=total_rows,
            filtered_rows=max_filtered,
            execution_time_ms=elapsed,
        ),
        chart_config=primary.chart_config if primary else fallback_chart,
        panels=panels,
        panel_count=len(panels),
        presentation=presentation,
        scope_events=sorted(scope) if scope else None,
    )
