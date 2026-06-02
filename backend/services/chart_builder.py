"""图表数据构建服务。"""

from __future__ import annotations

from typing import List, Optional

from schemas.analysis import AnalysisPlan, ChartConfig, MetricDef
from services.event_display import display_name_for_event_ref, localize_records_for_plan
from services.panel_caliber import build_caliber_text_list, build_panel_caliber_detail

CHART_COLORS = [
    "#007AFF",
    "#FF9500",
    "#34C759",
    "#FF3B30",
    "#5856D6",
    "#AF52DE",
    "#FF2D55",
    "#00C7BE",
]

_LINE_LIKE = {"line", "multi_line", "area", "growth_rate"}


def _map_chart_type(visualization_type: str) -> str:
    if visualization_type in _LINE_LIKE:
        return "line"
    if visualization_type in ("horizontal_bar", "stacked_bar", "funnel_chart"):
        return visualization_type
    return visualization_type


def _build_title(
    plan: AnalysisPlan,
    *,
    events_index: dict | None = None,
    locale: str | None = None,
) -> str:
    event_label = display_name_for_event_ref(
        plan.matched_event,
        events_index,
        locale=locale,
    )
    metric_names = "、".join(metric.name for metric in plan.metrics[:3])
    if len(plan.metrics) > 3:
        metric_names += "等"
    return f"{event_label} - {metric_names}"


def _series_type(plan: AnalysisPlan, metric: MetricDef, index: int) -> str:
    viz_type = plan.visualization.chart_type
    if viz_type == "table":
        return "table"
    if viz_type == "pie":
        return "pie"
    if viz_type in ("bar", "horizontal_bar", "stacked_bar", "funnel_chart"):
        return "bar"
    if viz_type == "heatmap":
        return "heatmap"
    if viz_type == "gauge":
        return "gauge"
    if viz_type == "dual_axis":
        return "line"
    if viz_type in ("multi_line", "area", "line", "growth_rate"):
        return "line"
    return "line"


def _build_series(plan: AnalysisPlan) -> List[dict]:
    viz_type = plan.visualization.chart_type
    series: List[dict] = []
    metrics = plan.metrics
    if viz_type == "funnel_chart":
        metrics = [m for m in plan.metrics if m.id == "user_count"] or plan.metrics[:1]

    for index, metric in enumerate(metrics):
        item: dict = {
            "key": metric.id,
            "name": metric.name,
            "type": _series_type(plan, metric, index),
            "color": CHART_COLORS[index % len(CHART_COLORS)],
        }
        if viz_type == "dual_axis":
            item["yAxisIndex"] = 0 if index == 0 else 1
        if viz_type == "stacked_bar":
            item["stack"] = "total"
        if viz_type == "area":
            item["areaStyle"] = True
        series.append(item)

    return series


def _resolve_value_key(plan: AnalysisPlan) -> Optional[str]:
    if not plan.metrics:
        return None
    viz = plan.visualization.chart_type
    if viz == "growth_rate":
        return "growth_rate"
    if viz in ("gauge", "funnel_chart"):
        for candidate in (plan.metrics[0].id, "repeat_rate", "stickiness", "user_count"):
            return candidate
    if viz == "heatmap":
        return plan.metrics[0].id
    return plan.metrics[0].id


def build(
    plan: AnalysisPlan,
    data: list[dict],
    *,
    events_index: dict | None = None,
    locale: str | None = None,
) -> ChartConfig:
    """根据可视化计划与聚合数据组装 ChartConfig。"""
    records = localize_records_for_plan(
        data, plan, events_index, locale=locale
    )
    viz_type = plan.visualization.chart_type
    chart_type = _map_chart_type(viz_type)
    y_axis_keys = [metric.id for metric in plan.metrics]

    if viz_type == "pie" and plan.metrics:
        y_axis_keys = [plan.metrics[0].id]

    if viz_type == "dual_axis" and len(plan.metrics) >= 2:
        y_axis_keys = [plan.metrics[0].id, plan.metrics[1].id]

    if viz_type == "growth_rate":
        y_axis_keys = ["growth_rate"]

    if viz_type == "funnel_chart":
        y_axis_keys = ["user_count"]
    elif viz_type == "gauge" and data:
        row = data[0]
        for key in ("repeat_rate", "stickiness", "user_count", "conversion_rate"):
            if key in row:
                y_axis_keys = [key]
                break

    sub_axis_key: Optional[str] = None
    if viz_type == "heatmap":
        sub_axis_key = plan.sub_dimension

    caliber_detail = build_panel_caliber_detail(
        plan, events_index=events_index, locale=locale
    )

    return ChartConfig(
        chart_type=chart_type if viz_type not in (
            "horizontal_bar", "stacked_bar", "heatmap", "gauge", "funnel_chart", "area"
        ) else viz_type,
        title=_build_title(plan, events_index=events_index, locale=locale),
        x_axis_key=plan.dimension,
        y_axis_keys=y_axis_keys,
        sub_axis_key=sub_axis_key,
        value_key=_resolve_value_key(plan),
        series=_build_series(plan),
        data=records,
        calibers=build_caliber_text_list(plan, caliber_detail),
        caliber_detail=caliber_detail,
    )
