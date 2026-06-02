"""代码侧数据可行性校验 — 对 LLM 提出的 data_requirements 做确定性检查。"""

from __future__ import annotations

from typing import List, Optional, Set

import pandas as pd

from schemas.agent_plan import (
    AgentContextBundle,
    DataFeasibilityCheck,
    DataRequirementSpec,
    VisualizationProposal,
)
from schemas.analysis import (
    AnalysisPlan,
    StatisticalCaliber,
    VisualizationDef,
)
from services.analysis_registry import (
    get_allowed_chart_types,
    validate_analysis_type,
)
from services.csv_processor import (
    _find_event_column,
    _find_time_column,
    parse_time_values,
    process_csv,
)
from services.event_mapping import infer_csv_filter_for_comparison, sanitize_csv_event_filter
from services.field_resolver import resolve_event
from services.metadata_resolver import MetadataResolverError, resolve


def _requirements_to_plan(
    proposal: VisualizationProposal,
    context: AgentContextBundle,
) -> AnalysisPlan:
    dr: DataRequirementSpec = proposal.data_requirements
    lookup = context.dictionary
    csv_filter = dr.csv_event_filter or lookup.csv_event_filter
    comparison = dr.comparison_events or lookup.comparison_events
    return AnalysisPlan(
        analysis_type=proposal.analysis_type,  # type: ignore[arg-type]
        matched_event=lookup.matched_event,
        matched_module=lookup.matched_module,
        match_confidence=lookup.match_confidence,
        intent_confidence=context.intent.intent_confidence,
        exploratory_mode=context.intent.exploratory_mode,
        metrics=dr.metrics,
        statistical_caliber=StatisticalCaliber(
            dedup_method="按VIN去重",
            time_granularity="daily",
            description=context.story.narrative[:240],
        ),
        visualization=VisualizationDef(
            chart_type=proposal.chart_type,  # type: ignore[arg-type]
            layout=proposal.layout,
            reasoning=proposal.reasoning,
        ),
        dimension=dr.dimension,
        sub_dimension=dr.sub_dimension,
        filters=dr.filters,
        time_range=dr.time_range,
        comparison_events=comparison,
        top_n=dr.top_n,
        cohort_retention_days=dr.cohort_retention_days,
        period_unit=dr.period_unit,
        csv_event_filter=csv_filter,
        event_mapping_note=lookup.mapping_note,
    )


def check_data_feasibility(
    proposal: VisualizationProposal,
    context: AgentContextBundle,
    *,
    df: pd.DataFrame,
    columns: List[str],
    csv_event_names: List[str],
    events_index: dict,
    query: str = "",
) -> DataFeasibilityCheck:
    """校验提案数据是否可支撑分析；必要时 dry-run process_csv。"""
    issues: List[str] = []
    warnings: List[str] = []
    suggestions: List[str] = []
    dr = proposal.data_requirements
    lookup = context.dictionary

    try:
        validate_analysis_type(proposal.analysis_type)
    except ValueError as exc:
        issues.append(str(exc))

    allowed_charts = get_allowed_chart_types(proposal.analysis_type)
    if proposal.chart_type not in allowed_charts:
        issues.append(
            f"chart_type「{proposal.chart_type}」不在 {proposal.analysis_type} "
            f"允许范围 {allowed_charts} 内"
        )
        suggestions.append(f"请改用: {allowed_charts[0]}")

    pool = set(csv_event_names)
    csv_filter = sanitize_csv_event_filter(
        dr.csv_event_filter or lookup.csv_event_filter,
        csv_event_names,
    )
    if not csv_filter and lookup.matched_event:
        try:
            resolved = resolve_event(
                lookup.matched_event,
                events_index,
                csv_event_names=csv_event_names,
                query=query,
            )
            csv_filter = list(resolved.csv_labels or [])
        except Exception:
            pass
    if proposal.analysis_type == "funnel":
        comparison = dr.comparison_events or lookup.comparison_events or []
        if len(comparison) >= 2:
            csv_filter = infer_csv_filter_for_comparison(
                comparison,
                events_index,
                csv_event_names,
                query=query,
            )
    if not csv_filter:
        issues.append("csv_event_filter 为空或均不在数据池中，无法过滤事件")
        suggestions.append("请从数据池 event 列取值中重新选择 csv_event_filter")

    invalid_csv = [v for v in (dr.csv_event_filter or []) if v not in pool]
    if invalid_csv:
        issues.append(f"以下 event 取值不在数据池中: {invalid_csv[:5]}")

    event_col = _find_event_column(columns)
    if event_col is None:
        issues.append("CSV 缺少 event/事件 列")
    time_col = _find_time_column(columns)
    needs_time = proposal.analysis_type in {
        "time_series",
        "growth_rate",
        "cohort_retention",
        "heatmap_time",
        "first_touch_trend",
        "active_users",
        "new_vs_returning",
        "period_pattern",
    }
    if needs_time:
        if time_col is None:
            issues.append("该分析需要时间列，但 CSV 中未识别到 date/time 列")
        elif csv_filter and event_col:
            subset = df[df[event_col].astype(str).isin(csv_filter)]
            if len(subset) > 0:
                parsed = parse_time_values(subset[time_col], time_col)
                if parsed.notna().sum() == 0:
                    warnings.append(
                        "目标事件行的 time 列无法解析；若坚持时间分析请改 analysis_type"
                    )
                    suggestions.append(
                        "可改为 summary_kpi / event_comparison / funnel，或扩大 csv_event_filter"
                    )

    for metric in dr.metrics:
        if metric.type == "nunique" and metric.field:
            if metric.field not in columns:
                issues.append(f"去重字段 {metric.field} 不在 CSV 列中")

    filtered_rows = 0
    preview_rows = 0
    if not issues:
        try:
            plan = _requirements_to_plan(proposal, context)
            plan = plan.model_copy(update={"csv_event_filter": csv_filter})
            resolution = resolve(
                plan,
                events_index,
                csv_event_names=csv_event_names,
                csv_columns=columns,
                query=query,
            )
            event_def = resolution["event_def"]
            override: Optional[Set[str]] = set(csv_filter) if csv_filter else None
            data_df, execution = process_csv(
                plan,
                event_def,
                df=df,
                event_filter_override=override,
                events_index=events_index,
            )
            filtered_rows = execution.filtered_rows
            preview_rows = len(data_df)
            if execution.status == "failed":
                issues.append("数据处理失败（缺少必要列）")
            elif filtered_rows == 0:
                issues.append("过滤后无数据行（时间窗或 event 过滤过严）")
                suggestions.append("放宽 time_range、扩大 csv_event_filter，或更换 analysis_type")
            elif preview_rows == 0:
                issues.append("聚合结果为空，当前规格无法产出图表数据")
                if proposal.analysis_type == "funnel":
                    suggestions.append(
                        "检查 comparison_events 顺序与字典映射；漏斗至少需 2 个可映射步骤"
                    )
            else:
                unavailable = execution.unavailable_dimensions
                if unavailable:
                    warnings.append(
                        f"部分维度不可用: {', '.join(unavailable[:5])}"
                    )
        except MetadataResolverError as exc:
            issues.append(f"元数据解析失败: {exc}")
        except Exception as exc:
            issues.append(f"数据试算异常: {exc}")

    ready = len(issues) == 0 and preview_rows > 0
    return DataFeasibilityCheck(
        panel_id=proposal.panel_id,
        ready=ready,
        filtered_rows=filtered_rows,
        preview_rows=preview_rows,
        issues=issues,
        warnings=warnings,
        suggestions=suggestions,
    )


def check_all_proposals(
    proposals: List[VisualizationProposal],
    context: AgentContextBundle,
    *,
    df: pd.DataFrame,
    columns: List[str],
    csv_event_names: List[str],
    events_index: dict,
    query: str = "",
) -> List[DataFeasibilityCheck]:
    return [
        check_data_feasibility(
            proposal,
            context,
            df=df,
            columns=columns,
            csv_event_names=csv_event_names,
            events_index=events_index,
            query=query,
        )
        for proposal in proposals
    ]
