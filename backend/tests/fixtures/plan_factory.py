"""为各 analysis_type 构造可跑通 process_csv 的最小 Carlog 计划。"""

from __future__ import annotations

from schemas.analysis import (
    AnalysisPlan,
    MetricDef,
    StatisticalCaliber,
    TimeRange,
    VisualizationDef,
)
from services.analysis_registry import (
    ANALYSIS_SPEC_BY_ID,
    EVENT_NAME_DIMENSION,
    get_analysis_spec,
)

CARLOG_EVENT = "Carlog_进入"
CARLOG_MODULE = "Carlog"
CARLOG_COMPARISON = ["Carlog_进入", "Carlog_录制", "Carlog_退出"]
CARLOG_CSV_STEPS = ["carlog_entry", "carlog_record", "carlog_exit"]

_DEFAULT_CALIBER = StatisticalCaliber(
    dedup_method="按VIN去重",
    time_granularity="daily",
    description="测试口径",
)
_DEFAULT_TIME = TimeRange(type="last_n_days", value=30)


def _viz(chart_type: str | None, analysis_type: str) -> VisualizationDef:
    spec = get_analysis_spec(analysis_type)
    ct = chart_type or (spec["default_chart"] if spec else "bar")
    return VisualizationDef(chart_type=ct, layout="single", reasoning="coverage test")


def _base(**kwargs) -> AnalysisPlan:
    analysis_type = kwargs.pop("analysis_type")
    metrics = kwargs.pop(
        "metrics",
        [MetricDef(id="pv", name="触发次数", type="count")],
    )
    return AnalysisPlan(
        analysis_type=analysis_type,
        matched_event=CARLOG_EVENT,
        matched_module=CARLOG_MODULE,
        match_confidence="high",
        metrics=metrics,
        visualization=kwargs.pop("visualization", _viz(None, analysis_type)),
        dimension=kwargs.pop("dimension", "date"),
        filters={},
        time_range=_DEFAULT_TIME,
        statistical_caliber=_DEFAULT_CALIBER,
        **kwargs,
    )


def build_plan_for_type(
    analysis_type: str,
    *,
    chart_type: str | None = None,
) -> AnalysisPlan:
    """按 analysis_type 返回最小合法 AnalysisPlan（Carlog 域）。"""
    spec = ANALYSIS_SPEC_BY_ID.get(analysis_type)
    if not spec:
        raise ValueError(f"unknown analysis_type: {analysis_type}")

    if analysis_type == "time_series":
        return _base(
            analysis_type=analysis_type,
            visualization=_viz(chart_type or "line", analysis_type),
            metrics=[
                MetricDef(id="pv", name="PV", type="count"),
                MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
            ],
        )
    if analysis_type == "dimension_breakdown":
        return _base(
            analysis_type=analysis_type,
            dimension="event",
            visualization=_viz(chart_type or "bar", analysis_type),
            metrics=[MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code")],
        )
    if analysis_type == "top_n_ranking":
        return _base(
            analysis_type=analysis_type,
            dimension="event",
            top_n=5,
            visualization=_viz(chart_type or "horizontal_bar", analysis_type),
        )
    if analysis_type == "usage_retention":
        return _base(
            analysis_type=analysis_type,
            dimension="使用次数分组",
            visualization=_viz(chart_type or "bar", analysis_type),
            metrics=[MetricDef(id="vehicle_count", name="车辆数", type="count")],
        )
    if analysis_type == "usage_distribution":
        return _base(
            analysis_type=analysis_type,
            dimension="使用次数分组",
            visualization=_viz(chart_type or "horizontal_bar", analysis_type),
            metrics=[MetricDef(id="vehicle_count", name="车辆数", type="count")],
        )
    if analysis_type == "active_days_distribution":
        return _base(
            analysis_type=analysis_type,
            dimension="活跃天数分组",
            visualization=_viz(chart_type or "bar", analysis_type),
            metrics=[MetricDef(id="vehicle_count", name="车辆数", type="count")],
        )
    if analysis_type == "penetration":
        return _base(
            analysis_type=analysis_type,
            visualization=_viz(chart_type or "line", analysis_type),
            metrics=[
                MetricDef(id="pv", name="PV", type="count"),
                MetricDef(
                    id="penetration_rate",
                    name="渗透率",
                    type="formula",
                    formula="uv / pv",
                    formula_components=["uv", "pv"],
                ),
                MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
            ],
        )
    if analysis_type == "cross_dimension":
        return _base(
            analysis_type=analysis_type,
            dimension="date",
            sub_dimension=EVENT_NAME_DIMENSION,
            visualization=_viz(chart_type or "stacked_bar", analysis_type),
            comparison_events=CARLOG_COMPARISON,
        )
    if analysis_type == "summary_kpi":
        return _base(
            analysis_type=analysis_type,
            dimension="_summary",
            visualization=_viz(chart_type or "table", analysis_type),
            metrics=[
                MetricDef(id="pv", name="PV", type="count"),
                MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
            ],
        )
    if analysis_type == "period_pattern":
        return _base(
            analysis_type=analysis_type,
            period_unit="hour",
            visualization=_viz(chart_type or "bar", analysis_type),
        )
    if analysis_type == "new_vs_returning":
        return _base(
            analysis_type=analysis_type,
            dimension="用户类型",
            visualization=_viz(chart_type or "pie", analysis_type),
            metrics=[MetricDef(id="vehicle_count", name="车辆数", type="count")],
        )
    if analysis_type == "repeat_rate":
        return _base(
            analysis_type=analysis_type,
            dimension="_summary",
            visualization=_viz(chart_type or "gauge", analysis_type),
            metrics=[
                MetricDef(
                    id="repeat_rate",
                    name="复访率",
                    type="formula",
                    formula="repeat_vins / total_vins",
                    formula_components=["repeat_vins", "total_vins"],
                ),
            ],
        )
    if analysis_type == "cohort_retention":
        return _base(
            analysis_type=analysis_type,
            dimension="队列日期",
            sub_dimension="留存天数",
            cohort_retention_days=[1, 3, 7],
            visualization=_viz(chart_type or "line", analysis_type),
            metrics=[
                MetricDef(id="retention_rate", name="留存率", type="count"),
                MetricDef(id="retained_users", name="留存车辆", type="count"),
            ],
        )
    if analysis_type == "funnel":
        return _base(
            analysis_type=analysis_type,
            dimension="漏斗步骤",
            comparison_events=CARLOG_COMPARISON,
            csv_event_filter=CARLOG_CSV_STEPS,
            visualization=_viz(chart_type or "funnel_chart", analysis_type),
            metrics=[
                MetricDef(id="user_count", name="到达车辆数", type="count"),
                MetricDef(id="conversion_rate", name="步间转化率(%)", type="count"),
            ],
        )
    if analysis_type == "event_comparison":
        return _base(
            analysis_type=analysis_type,
            dimension=EVENT_NAME_DIMENSION,
            comparison_events=CARLOG_COMPARISON,
            visualization=_viz(chart_type or "bar", analysis_type),
            metrics=[
                MetricDef(id="pv", name="PV", type="count"),
                MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
            ],
        )
    if analysis_type == "active_users":
        return _base(
            analysis_type=analysis_type,
            dimension="活跃指标",
            visualization=_viz(chart_type or "bar", analysis_type),
            metrics=[
                MetricDef(id="dau", name="DAU", type="count"),
                MetricDef(id="wau", name="WAU", type="count"),
                MetricDef(id="mau", name="MAU", type="count"),
            ],
        )
    if analysis_type == "growth_rate":
        return _base(
            analysis_type=analysis_type,
            visualization=_viz(chart_type or "line", analysis_type),
            metrics=[
                MetricDef(
                    id="growth_rate",
                    name="环比增长率",
                    type="formula",
                    formula="(uv - prev_uv) / prev_uv",
                    formula_components=["uv", "prev_uv"],
                ),
                MetricDef(id="uv", name="按车去重", type="nunique", field="vin_code"),
            ],
        )
    if analysis_type == "stickiness":
        return _base(
            analysis_type=analysis_type,
            dimension="_summary",
            visualization=_viz(chart_type or "gauge", analysis_type),
            metrics=[
                MetricDef(
                    id="stickiness",
                    name="粘性",
                    type="formula",
                    formula="dau / mau",
                    formula_components=["dau", "mau"],
                ),
            ],
        )
    if analysis_type == "percentile_stats":
        return _base(
            analysis_type=analysis_type,
            dimension="分位点",
            visualization=_viz(chart_type or "bar", analysis_type),
            metrics=[MetricDef(id="usage_count", name="使用次数", type="count")],
        )
    if analysis_type == "heatmap_time":
        return _base(
            analysis_type=analysis_type,
            dimension="date",
            sub_dimension="时段",
            visualization=_viz(chart_type or "heatmap", analysis_type),
        )
    if analysis_type == "first_touch_trend":
        return _base(
            analysis_type=analysis_type,
            visualization=_viz(chart_type or "area", analysis_type),
            metrics=[
                MetricDef(id="new_users", name="新增用户", type="nunique", field="vin_code"),
            ],
        )

    return _base(
        analysis_type=analysis_type,
        visualization=_viz(chart_type, analysis_type),
    )


def event_filter_for_type(analysis_type: str) -> set[str]:
    if analysis_type in ("funnel", "event_comparison", "cross_dimension"):
        return set(CARLOG_CSV_STEPS)
    return {"carlog_entry"}
