"""面板统计口径、图表构成与指标说明。"""

from __future__ import annotations

from typing import List, Optional

from schemas.analysis import AnalysisPlan, MetricDef, PanelCaliberDetail
from services.analysis_registry import (
    ACTIVE_DAYS_BUCKET_DIMENSION,
    ACTIVE_USER_DIMENSION,
    CHART_TYPE_CATALOG,
    COHORT_DATE_DIMENSION,
    DAY_OF_WEEK_DIMENSION,
    FUNNEL_STEP_DIMENSION,
    HOUR_OF_DAY_DIMENSION,
    PERCENTILE_DIMENSION,
    SUMMARY_DIMENSION,
    USAGE_BUCKET_DIMENSION,
    USER_TYPE_DIMENSION,
    get_analysis_spec,
)
from services.event_display import display_name_for_event_ref

_EXPLORATORY_CALIBER_PREFIX = "探索性分析："
_GENERIC_CALIBERS = frozenset({"测试口径", "test", ""})

_GRANULARITY_ZH = {
    "daily": "日",
    "hourly": "小时",
    "weekly": "周",
    "monthly": "月",
}

_FIELD_LABELS: dict[str, str] = {
    "vin_code": "车辆 VIN",
    "user_id": "用户 ID",
}

_COMPONENT_LABELS: dict[str, str] = {
    "pv": "触发次数",
    "uv": "独立车辆数",
    "dau": "日活跃车辆数",
    "wau": "周活跃车辆数",
    "mau": "月活跃车辆数",
    "total_vehicles": "基准车辆总数",
    "user_count": "到达车辆数",
    "count": "记录条数",
    "repeat_vins": "复访车辆数",
    "total_vins": "全部车辆数",
    "prev_uv": "上一期独立车辆数",
}


def _field_label(field: str) -> str:
    return _FIELD_LABELS.get(field, field)


def _component_label(component_id: str) -> str:
    return _COMPONENT_LABELS.get(component_id, component_id)


def _granularity_label(granularity: str) -> str:
    return _GRANULARITY_ZH.get(granularity, granularity)


def _metrics_label(plan: AnalysisPlan) -> str:
    return "、".join(metric.name for metric in plan.metrics)


def _chart_type_name(chart_type: str) -> str:
    meta = CHART_TYPE_CATALOG.get(chart_type)
    return meta["name"] if meta else chart_type


def _chart_render_note(plan: AnalysisPlan) -> Optional[str]:
    chart_type = plan.visualization.chart_type
    meta = CHART_TYPE_CATALOG.get(chart_type)
    if not meta:
        return None
    return f"本图采用{meta['name']}：{meta['use_when']}"


def _dimension_label(plan: AnalysisPlan) -> str:
    dim = plan.dimension or "date"
    if dim == SUMMARY_DIMENSION:
        return "汇总（不分组）"
    if dim == "date":
        return "日期"
    return dim


def _time_scope_note(plan: AnalysisPlan) -> Optional[str]:
    tr = plan.time_range
    if not tr:
        return None
    if tr.type == "last_n_days" and tr.value:
        return f"分析窗口：最近 {tr.value} 天内的数据"
    if tr.type == "absolute" and tr.start and tr.end:
        return f"分析窗口：{tr.start} 至 {tr.end}"
    if tr.type == "all":
        return "分析窗口：上传数据中的全部时间范围"
    return None


def _resolve_caliber_description(plan: AnalysisPlan, description: str) -> str:
    spec = get_analysis_spec(plan.analysis_type or "")
    if not spec:
        return description

    use_spec = (
        description.startswith(_EXPLORATORY_CALIBER_PREFIX)
        or description.strip() in _GENERIC_CALIBERS
        or len(description.strip()) < 12
    )
    base = spec["description"] if use_spec else description

    dim = plan.dimension
    if dim and dim not in (
        SUMMARY_DIMENSION,
        "date",
        USER_TYPE_DIMENSION,
        USAGE_BUCKET_DIMENSION,
        ACTIVE_DAYS_BUCKET_DIMENSION,
        COHORT_DATE_DIMENSION,
        FUNNEL_STEP_DIMENSION,
        ACTIVE_USER_DIMENSION,
        PERCENTILE_DIMENSION,
        HOUR_OF_DAY_DIMENSION,
        DAY_OF_WEEK_DIMENSION,
    ):
        if dim not in base:
            return f"{base}（按「{dim}」分组）"
    return base


def _formula_natural_language(metric: MetricDef, plan: AnalysisPlan) -> str:
    name = metric.name
    expr = (metric.formula or "").strip()
    expr_compact = expr.replace(" ", "")
    metric_id = metric.id.lower()

    known: dict[str, str] = {
        "uv/pv": f"{name}：独立车辆数 ÷ 触发总次数",
        "uv_vin/total_vehicles": f"{name}：独立车辆数 ÷ 基准车辆总数 × 100",
        "dau/mau": f"{name}：日活跃车辆数 ÷ 月活跃车辆数 × 100",
        "count/unique_vin": f"{name}：触发总次数 ÷ 独立车辆数",
        "repeat_vins/total_vins": f"{name}：复访车辆数 ÷ 全部车辆数 × 100",
        "(uv-prev_uv)/prev_uv": f"{name}：（本期独立车辆数 − 上期独立车辆数）÷ 上期独立车辆数 × 100",
    }
    if expr_compact in known:
        return known[expr_compact]

    if metric.formula_components and len(metric.formula_components) >= 2 and "/" in expr:
        left = _component_label(metric.formula_components[0])
        right = _component_label(metric.formula_components[1])
        suffix = " × 100" if ("率" in name or "rate" in metric_id) else ""
        return f"{name}：{left} ÷ {right}{suffix}"

    if metric.formula_components:
        parts = "、".join(_component_label(item) for item in metric.formula_components)
        return f"{name}：由 {parts} 组合计算得出"

    if expr:
        return f"{name}：按表达式 {expr} 计算得出"
    return f"{name}：复合指标"


def _metric_formula_description(metric: MetricDef, plan: AnalysisPlan) -> str:
    analysis_type = plan.analysis_type or ""
    metric_id = metric.id.lower()
    name = metric.name

    if analysis_type == "growth_rate" and metric_id == "growth_rate":
        return f"{name}：相邻两个{_granularity_label(plan.statistical_caliber.time_granularity)}粒度之间的环比变化百分比"
    if analysis_type == "stickiness" and metric_id == "stickiness":
        return f"{name}：窗口最后一日 DAU ÷ 窗口内 MAU × 100"
    if analysis_type == "repeat_rate":
        return f"{name}：分析窗口内触发 ≥2 次的 VIN 数 ÷ 窗口内全部 VIN 数 × 100"
    if analysis_type == "cohort_retention":
        if metric_id == "retention_rate":
            return f"{name}：该队列在指定留存天仍活跃的 VIN 数 ÷ 队列规模 × 100"
        if metric_id == "retained_users":
            return f"{name}：该队列在指定留存天仍活跃的 VIN 数"
    if analysis_type == "new_vs_returning" and metric_id == "vehicle_count":
        return f"{name}：按「用户类型」分组后的独立 VIN 数量"
    if analysis_type == "first_touch_trend" and metric_id == "new_users":
        return f"{name}：当日首次触发所选事件的独立 VIN 数量"
    if analysis_type in ("usage_retention", "usage_distribution", "active_days_distribution"):
        if metric_id == "vehicle_count":
            return f"{name}：落入当前分桶的独立 VIN 数量"
    if analysis_type == "active_users":
        if metric_id == "dau":
            return "DAU：分析窗口最后一日有触发的独立 VIN 数"
        if metric_id == "wau":
            return "WAU：分析窗口最后 7 日（含最后一日）有触发的独立 VIN 数"
        if metric_id == "mau":
            return "MAU：分析窗口最后 30 日（含最后一日）有触发的独立 VIN 数"
    if analysis_type == "percentile_stats" and metric_id == "usage_count":
        return f"{name}：所有 VIN 使用次数分布在该分位点上的数值"
    if analysis_type == "funnel" and metric_id == "conversion_rate":
        return f"{name}：本漏斗步骤到达车辆数 ÷ 上一步到达车辆数 × 100"
    if analysis_type == "funnel" and metric_id == "user_count":
        return f"{name}：按顺序完成前序步骤后到达本步骤的独立 VIN 数"

    if metric.type == "count":
        if metric_id == "pv" or name.upper() == "PV" or "触发" in name:
            return f"{name}：统计事件触发记录的总条数"
        if metric_id in ("vehicle_count", "user_count"):
            return f"{name}：满足当前分组条件的独立 VIN 数量"
        return f"{name}：统计满足筛选条件的记录条数"

    if metric.type == "nunique":
        field = metric.field or "vin_code"
        return f"{name}：对 {_field_label(field)} 去重计数"

    if metric.type == "formula":
        return _formula_natural_language(metric, plan)

    return name


def _grouping_rules(plan: AnalysisPlan) -> List[str]:
    analysis_type = plan.analysis_type or ""

    if analysis_type == "new_vs_returning":
        return [
            "新用户：在所选事件的全部历史记录中，该 VIN 的首次触发时间不早于当前分析窗口起点",
            "老用户：在所选事件的全部历史记录中，该 VIN 在分析窗口开始前已有触发记录",
            "统计范围：仅计入当前分析窗口内至少触发过一次的 VIN",
        ]
    if analysis_type == "first_touch_trend":
        return [
            "每个 VIN 仅在其首次触发所选事件的日期计入一次「新增用户」",
        ]
    if analysis_type == "usage_retention":
        return [
            "先统计每个 VIN 在分析窗口内的触发总次数",
            "按「使用1次」至「使用10次」及「使用10次以上」共 11 个分桶统计车辆数",
        ]
    if analysis_type == "usage_distribution":
        return [
            "先统计每个 VIN 在分析窗口内的触发总次数",
            "按「使用 N 次」逐桶划分（1 次、2 次、3 次…），统计各桶内 VIN 数",
        ]
    if analysis_type == "active_days_distribution":
        return [
            "先统计每个 VIN 在分析窗口内有触发记录的天数",
            "按「活跃 N 天」分桶（超过 10 天合并为「活跃10天以上」）",
        ]
    if analysis_type == "cohort_retention":
        days = plan.cohort_retention_days or [1, 3, 7, 14, 30]
        day_text = "、".join(f"D+{d}" for d in days)
        return [
            "按 VIN 在所选事件中的首次触发日期划分队列",
            f"对每个队列追踪 {day_text} 仍活跃的 VIN 并计算留存率",
        ]
    if analysis_type == "funnel" and plan.comparison_events:
        steps = " → ".join(str(s) for s in plan.comparison_events)
        return [
            f"漏斗步骤（按顺序）：{steps}",
            "每步仅统计按 VIN 去重后、顺序完成前序步骤的车辆",
        ]
    if analysis_type == "percentile_stats":
        return [
            "先统计每个 VIN 在分析窗口内的触发总次数",
            "再对所有 VIN 的使用次数求 P50 / P75 / P90 / P99 分位点",
        ]
    if analysis_type == "repeat_rate":
        return [
            "复访车辆：分析窗口内触发次数 ≥2 的 VIN",
            "全部车辆：分析窗口内至少触发过 1 次的 VIN",
        ]
    if analysis_type == "stickiness":
        return [
            "以分析窗口最后一日为基准日计算 DAU",
            "以窗口最后 30 日为范围计算 MAU",
        ]
    return []


def _chart_layout_notes(plan: AnalysisPlan) -> List[str]:
    analysis_type = plan.analysis_type or ""
    chart_type = plan.visualization.chart_type
    granularity = _granularity_label(plan.statistical_caliber.time_granularity)
    metrics = _metrics_label(plan)
    dim = _dimension_label(plan)
    notes: List[str] = []

    scope = _time_scope_note(plan)
    if scope:
        notes.append(scope)

    if analysis_type == "time_series":
        notes.extend([
            f"横轴：时间（{granularity}粒度），缺失日期补 0",
            f"纵轴：{metrics}",
            "每个时间点汇总所选事件在该时段内的指标",
        ])
    elif analysis_type == "dimension_breakdown":
        notes.extend([
            f"横轴：「{dim}」各分类取值",
            f"纵轴：{metrics}",
            "将分析窗口内记录按该维度分组后分别统计",
        ])
    elif analysis_type == "top_n_ranking":
        top_n = plan.top_n or 10
        notes.extend([
            f"按「{dim}」分组统计 {metrics} 后降序排列，取前 {top_n} 名",
            "排名越靠前，该分类的指标值越大",
        ])
    elif analysis_type == "usage_retention":
        notes.extend([
            "横轴：使用次数分桶（使用1次 … 使用10次、使用10次以上）",
            "纵轴：车辆数",
        ])
    elif analysis_type == "usage_distribution":
        notes.extend([
            "横轴：使用次数分桶（使用1次、使用2次、使用3次…）",
            "纵轴：车辆数",
        ])
    elif analysis_type == "active_days_distribution":
        notes.extend([
            "横轴：活跃天数分桶",
            "纵轴：车辆数",
        ])
    elif analysis_type == "penetration":
        if plan.dimension == "date" or dim == "日期":
            notes.extend([
                f"横轴：日期（{granularity}粒度）",
                f"纵轴：{metrics}",
            ])
        else:
            notes.extend([
                f"横轴：「{dim}」各分类",
                f"纵轴：{metrics}",
            ])
    elif analysis_type == "cross_dimension":
        sub = plan.sub_dimension or "次维度"
        notes.extend([
            f"横轴：主维度「{dim}」",
            f"系列/堆叠：次维度「{sub}」各取值",
            f"纵轴：{metrics}",
        ])
    elif analysis_type == "summary_kpi":
        notes.append("不做分组，直接汇总整个分析窗口")
        if chart_type == "table":
            notes.append(f"表格展示各指标数值：{metrics}")
        elif chart_type == "gauge":
            notes.append(f"仪表盘展示核心指标：{metrics}")
        else:
            notes.append(f"图表对比各汇总指标：{metrics}")
    elif analysis_type == "period_pattern":
        unit = plan.period_unit or "hour"
        if unit == "weekday":
            notes.extend([
                "横轴：星期（周一至周日）",
                f"纵轴：{metrics}",
                "将窗口内所有记录按星期归类汇总（不区分具体日期）",
            ])
        else:
            notes.extend([
                "横轴：一天中的小时（0–23 时）",
                f"纵轴：{metrics}",
                "将窗口内所有记录按小时归类汇总（不区分具体日期）",
            ])
    elif analysis_type == "new_vs_returning":
        notes.extend([
            "分类轴：用户类型（新用户 / 老用户）",
            "数值：各类型独立 VIN 数",
        ])
        if chart_type == "pie":
            notes.append("扇区面积代表该类型占全部车辆的比例")
        else:
            notes.append("柱高代表各类型车辆数量")
    elif analysis_type == "repeat_rate":
        notes.append("单值展示复访率（%），表示窗口内重复触发车辆占比")
    elif analysis_type == "cohort_retention":
        if chart_type == "heatmap":
            notes.extend([
                "横轴：队列日期（首次使用日）",
                "纵轴：留存天数（D+1、D+3…）",
                "色块深浅：留存率高低",
            ])
        else:
            notes.extend([
                "横轴：队列日期或留存天数（取决于图表配置）",
                "纵轴：留存率（%）",
                "每条线/每组柱代表一个观测留存天",
            ])
    elif analysis_type == "funnel":
        notes.extend([
            "步骤轴：漏斗各步骤（按事件顺序）",
            "宽度/柱高：各步到达的独立 VIN 数",
            "步间转化率 = 本步车辆数 ÷ 上步车辆数",
        ])
    elif analysis_type == "event_comparison":
        if plan.dimension in ("date", "日期") or plan.sub_dimension:
            notes.extend([
                "横轴：日期",
                f"每条线/每组柱：一个对比事件的 {metrics}",
            ])
        else:
            notes.extend([
                "横轴：各对比事件",
                f"纵轴：{metrics}",
            ])
    elif analysis_type == "active_users":
        notes.extend([
            "横轴：DAU / WAU / MAU 三类活跃指标",
            "纵轴：对应独立 VIN 数",
            "三类指标在同一窗口末时点分别计算",
        ])
    elif analysis_type == "growth_rate":
        notes.extend([
            f"横轴：日期（{granularity}粒度）",
            "纵轴：环比增长率（%）",
            "基于日粒度独立 VIN 序列，计算相邻时点的变化率",
        ])
    elif analysis_type == "stickiness":
        notes.append("单值展示 DAU/MAU 粘性比率（%）")
    elif analysis_type == "percentile_stats":
        notes.extend([
            "横轴：分位点（P50 / P75 / P90 / P99）",
            "纵轴：使用次数",
            "反映车辆使用频次的分布形态",
        ])
    elif analysis_type == "heatmap_time":
        notes.extend([
            "横轴：日期",
            "纵轴：时段（0–23 时）",
            "色块深浅：该日该时段的触发次数",
        ])
    elif analysis_type == "first_touch_trend":
        notes.extend([
            f"横轴：日期（{granularity}粒度）",
            "纵轴：新增用户数",
            "每个 VIN 仅在其首次触发日计入一次",
        ])
    else:
        spec = get_analysis_spec(analysis_type)
        if spec:
            notes.append(spec["description"])
        notes.append(f"横轴/分类：{dim}；指标：{metrics}")

    render = _chart_render_note(plan)
    if render:
        notes.append(render)

    return notes


def _panel_event_refs(plan: AnalysisPlan) -> List[str]:
    if plan.comparison_events and len(plan.comparison_events) >= 2:
        if plan.analysis_type in ("funnel", "event_comparison"):
            return [str(item) for item in plan.comparison_events]
    if plan.csv_event_filter:
        return [str(item) for item in plan.csv_event_filter]
    if plan.matched_event:
        return [plan.matched_event]
    return []


def build_panel_caliber_detail(
    plan: AnalysisPlan,
    *,
    events_index: dict | None = None,
    locale: str | None = None,
) -> PanelCaliberDetail:
    caliber = plan.statistical_caliber
    events: List[str] = []
    seen: set[str] = set()
    for ref in _panel_event_refs(plan):
        label = display_name_for_event_ref(ref, events_index, locale=locale)
        if label and label not in seen:
            seen.add(label)
            events.append(label)

    formulas = [_metric_formula_description(metric, plan) for metric in plan.metrics]

    return PanelCaliberDetail(
        description=_resolve_caliber_description(plan, caliber.description),
        dedup_method=caliber.dedup_method,
        time_granularity=caliber.time_granularity,
        events=events,
        formulas=formulas,
        grouping_rules=_grouping_rules(plan),
        chart_layout=_chart_layout_notes(plan),
    )


def build_caliber_text_list(plan: AnalysisPlan, detail: PanelCaliberDetail) -> List[str]:
    """供 ChartConfig.calibers 使用的扁平文本列表。"""
    calibers = [
        detail.description,
        f"去重方式：{detail.dedup_method}",
        f"聚合粒度：{detail.time_granularity}",
    ]
    if detail.chart_layout:
        calibers.append("图表构成：" + "；".join(detail.chart_layout))
    if detail.events:
        calibers.append(f"使用事件：{'、'.join(detail.events)}")
    if detail.grouping_rules:
        calibers.append("分组规则：" + "；".join(detail.grouping_rules))
    if detail.formulas:
        calibers.append("指标计算：" + "；".join(detail.formulas))
    if plan.analysis_type:
        calibers.append(f"分析类型：{plan.analysis_type}")
    calibers.append(f"图表类型：{plan.visualization.chart_type}")
    return calibers
