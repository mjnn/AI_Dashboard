"""埋点分析类型注册表 — LLM 只能从此枚举中选择 analysis_type。"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from schemas.analysis import AnalysisPlan

AnalysisType = Literal[
    "time_series",
    "dimension_breakdown",
    "top_n_ranking",
    "usage_retention",
    "usage_distribution",
    "active_days_distribution",
    "penetration",
    "cross_dimension",
    "summary_kpi",
    "period_pattern",
    "new_vs_returning",
    "repeat_rate",
    "cohort_retention",
    "funnel",
    "event_comparison",
    "active_users",
    "growth_rate",
    "stickiness",
    "percentile_stats",
    "heatmap_time",
    "first_touch_trend",
]

# 衍生维度常量（后端计算，CSV 中不存在）
USAGE_BUCKET_DIMENSION = "使用次数分组"
USER_TYPE_DIMENSION = "用户类型"
HOUR_OF_DAY_DIMENSION = "时段"
DAY_OF_WEEK_DIMENSION = "星期"
COHORT_DATE_DIMENSION = "队列日期"
RETENTION_DAY_DIMENSION = "留存天数"
FUNNEL_STEP_DIMENSION = "漏斗步骤"
EVENT_NAME_DIMENSION = "event"
ACTIVE_USER_DIMENSION = "活跃指标"
PERCENTILE_DIMENSION = "分位点"
ACTIVE_DAYS_BUCKET_DIMENSION = "活跃天数分组"
SUMMARY_DIMENSION = "_summary"

_TIME_DIMENSIONS = {"date", "time", "timestamp", "datetime", "日期", "时间"}
_USAGE_BUCKET_PATTERN = re.compile(
    r"use_count|usage_count|使用次数|次数分组|频次|留存|retention|frequency",
    re.IGNORECASE,
)
_WEEKDAY_PATTERN = re.compile(r"星期|weekday|周几|week_day", re.IGNORECASE)
_HOUR_PATTERN = re.compile(r"时段|hour|小时|hour_of_day", re.IGNORECASE)
_NEW_USER_PATTERN = re.compile(r"新用户|老用户|回访|新老|new.*return|returning", re.IGNORECASE)
_FUNNEL_PATTERN = re.compile(r"漏斗|转化|funnel|conversion", re.IGNORECASE)
_COMPARE_PATTERN = re.compile(r"对比|比较|compare|vs", re.IGNORECASE)
_TOP_N_PATTERN = re.compile(r"top\s*\d+|前\s*\d+|排名|排行", re.IGNORECASE)
_GROWTH_PATTERN = re.compile(r"环比|同比|增长率|growth|mom|yoy", re.IGNORECASE)
_COHORT_PATTERN = re.compile(r"队列|cohort", re.IGNORECASE)
_PERCENTILE_PATTERN = re.compile(r"分位|p50|p90|percentile", re.IGNORECASE)
_HEATMAP_PATTERN = re.compile(r"热力|heatmap", re.IGNORECASE)
_DAU_PATTERN = re.compile(r"dau|wau|mau|日活|周活|月活|活跃用户", re.IGNORECASE)
_STICKINESS_PATTERN = re.compile(r"粘性|stickiness|dau/mau", re.IGNORECASE)
_FIRST_TOUCH_PATTERN = re.compile(r"首次|新增用户|first.?touch|新触达", re.IGNORECASE)
_ACTIVE_DAYS_PATTERN = re.compile(r"活跃天数|活跃.*天", re.IGNORECASE)

DERIVED_DIMENSIONS = {
    USAGE_BUCKET_DIMENSION,
    USER_TYPE_DIMENSION,
    HOUR_OF_DAY_DIMENSION,
    DAY_OF_WEEK_DIMENSION,
    COHORT_DATE_DIMENSION,
    RETENTION_DAY_DIMENSION,
    FUNNEL_STEP_DIMENSION,
    EVENT_NAME_DIMENSION,
    ACTIVE_USER_DIMENSION,
    PERCENTILE_DIMENSION,
    ACTIVE_DAYS_BUCKET_DIMENSION,
    SUMMARY_DIMENSION,
}


class AnalysisTypeSpec(TypedDict):
    id: str
    name: str
    description: str
    dimension: str
    chart_types: list[str]
    default_chart: str
    chart_guide: str
    metric_hint: str
    example_query: str
    extra_fields: str


ChartTypeId = Literal[
    "line",
    "area",
    "multi_line",
    "dual_axis",
    "bar",
    "horizontal_bar",
    "stacked_bar",
    "pie",
    "table",
    "heatmap",
    "gauge",
    "funnel_chart",
]

CHART_TYPE_CATALOG: dict[str, dict[str, str]] = {
    "line": {
        "name": "折线图",
        "use_when": "连续时间趋势、队列留存曲线、增长率变化",
    },
    "area": {
        "name": "面积图",
        "use_when": "趋势+体量感，强调累计或流量规模（新增用户、PV趋势）",
    },
    "multi_line": {
        "name": "多折线图",
        "use_when": "同一图表对比多条时间序列（多指标、多事件、多队列）",
    },
    "dual_axis": {
        "name": "双轴图",
        "use_when": "两个量纲差异大的指标同屏对比（PV vs UV、次数 vs 率）",
    },
    "bar": {
        "name": "柱状图",
        "use_when": "分类对比、分布、排名（类别适中时）",
    },
    "horizontal_bar": {
        "name": "横向柱状图",
        "use_when": "Top N 排名、漏斗步骤、长标签分类、频次分桶",
    },
    "stacked_bar": {
        "name": "堆叠柱状图",
        "use_when": "交叉维度构成对比、多事件同柱堆叠、新老用户构成",
    },
    "pie": {
        "name": "饼图/环形图",
        "use_when": "占比分析（类别 ≤6 且强调部分占整体）",
    },
    "table": {
        "name": "表格",
        "use_when": "精确数值、多列 KPI、热力明细、汇总指标",
    },
    "heatmap": {
        "name": "热力图",
        "use_when": "二维交叉密度（日期×时段、队列×留存天）",
    },
    "gauge": {
        "name": "仪表盘",
        "use_when": "单一比率/KPI（复访率、粘性、渗透率快照）",
    },
    "funnel_chart": {
        "name": "漏斗图",
        "use_when": "多步骤转化漏斗，逐步收窄可视化",
    },
}

CHART_TYPE_IDS: set[str] = set(CHART_TYPE_CATALOG.keys())


def _spec(
    id: str,
    name: str,
    description: str,
    dimension: str,
    chart_types: list[str],
    default_chart: str,
    chart_guide: str,
    metric_hint: str,
    example_query: str,
    extra_fields: str = "",
) -> AnalysisTypeSpec:
    return {
        "id": id,
        "name": name,
        "description": description,
        "dimension": dimension,
        "chart_types": chart_types,
        "default_chart": default_chart,
        "chart_guide": chart_guide,
        "metric_hint": metric_hint,
        "example_query": example_query,
        "extra_fields": extra_fields,
    }


# 座舱埋点领域可枚举的分析模式（含完整图表选型范围）
ANALYSIS_CATALOG: list[AnalysisTypeSpec] = [
    _spec(
        "time_series", "时间趋势",
        "按日/时/周统计 PV、UV，时间轴自动补全",
        "date",
        ["line", "area", "multi_line", "dual_axis", "bar", "table"],
        "line",
        "默认折线；强调体量用面积图；PV+UV 用双轴或多折线",
        "count + nunique(vin_code)", "Carlog进入最近7天每日趋势",
    ),
    _spec(
        "dimension_breakdown", "维度分布",
        "按 CSV 列分组统计触发量/车辆数",
        "CSV列名",
        ["bar", "horizontal_bar", "pie", "stacked_bar", "table"],
        "bar",
        "类别少用饼图；标签长或排名感用横向柱；多维构成用堆叠柱",
        "count 或 nunique(vin_code)", "各车型的Carlog触发分布",
    ),
    _spec(
        "top_n_ranking", "Top N 排名",
        "按维度取值排序取前 N 名（降序）",
        "CSV列名",
        ["horizontal_bar", "bar", "table"],
        "horizontal_bar",
        "排名首选横向柱（标签可读性最好）；少量类别可用竖柱",
        "count 或 nunique(vin_code)", "Carlog触发量Top10车型",
        "top_n: 默认10",
    ),
    _spec(
        "usage_retention", "留存分桶",
        "VIN 使用次数分桶为「使用1次」「使用2次」，统计各桶车辆数",
        USAGE_BUCKET_DIMENSION,
        ["bar", "horizontal_bar", "pie", "table"],
        "bar",
        "两桶对比用柱图；强调占比用饼图；精确数值用表格",
        "count, id=vehicle_count", "Carlog使用1次和2次的车辆数",
    ),
    _spec(
        "usage_distribution", "频次分布",
        "VIN 使用次数全量分桶（1次/2次/3次/…）",
        USAGE_BUCKET_DIMENSION,
        ["bar", "horizontal_bar", "line", "area", "table"],
        "horizontal_bar",
        "分桶多时用横向柱；观察整体形态可用折线/面积",
        "count, id=vehicle_count", "Carlog各使用频次的车辆分布",
    ),
    _spec(
        "active_days_distribution", "活跃天数分布",
        "统计每 VIN 在周期内活跃了多少天，按天数分桶",
        ACTIVE_DAYS_BUCKET_DIMENSION,
        ["bar", "horizontal_bar", "pie", "stacked_bar", "table"],
        "bar",
        "分桶对比用柱图；占比看饼图；活跃结构用堆叠柱",
        "count, id=vehicle_count", "Carlog用户活跃天数分布",
    ),
    _spec(
        "penetration", "渗透率/复合指标",
        "formula 指标（如 PV/UV），配合时间或维度",
        "date 或 CSV列",
        ["line", "area", "dual_axis", "bar", "gauge", "table"],
        "line",
        "趋势用折线/面积；率值快照可用 gauge；PV 与率双轴",
        "formula + formula_components", "Carlog日渗透率趋势",
    ),
    _spec(
        "cross_dimension", "交叉分析",
        "两个维度交叉分组",
        "主维度",
        ["stacked_bar", "multi_line", "bar", "heatmap", "table"],
        "stacked_bar",
        "构成对比用堆叠柱；时间×分类用多折线；矩阵用热力图",
        "count 或 nunique", "按日和来源看Carlog触发量",
        "sub_dimension 必填",
    ),
    _spec(
        "summary_kpi", "汇总 KPI",
        "不分组，输出整体 PV/UV 等汇总指标",
        SUMMARY_DIMENSION,
        ["table", "gauge", "bar", "pie"],
        "table",
        "多指标用表格；单一核心 KPI 可用 gauge；2-3 指标对比可用柱/饼",
        "count + nunique(vin_code)", "Carlog进入总共多少次、多少辆车",
    ),
    _spec(
        "period_pattern", "时段规律",
        "按小时或星期几统计触发分布，发现使用高峰",
        f"{HOUR_OF_DAY_DIMENSION} 或 {DAY_OF_WEEK_DIMENSION}",
        ["bar", "line", "area", "horizontal_bar", "table"],
        "bar",
        "24 小时/7 天周期用柱图最直观；平滑趋势可用折线/面积",
        "count 或 nunique(vin_code)", "Carlog各时段触发分布",
        "period_unit: hour 或 weekday",
    ),
    _spec(
        "new_vs_returning", "新老用户",
        "周期内首次出现为「新用户」，之前已有记录为「老用户」",
        USER_TYPE_DIMENSION,
        ["pie", "bar", "stacked_bar", "horizontal_bar", "table"],
        "pie",
        "占比首选饼图；强调数量对比用柱图；构成变化用堆叠柱",
        "count, id=vehicle_count", "Carlog新老用户占比",
    ),
    _spec(
        "repeat_rate", "复访率",
        "周期内触发≥2次的 VIN 占全部 VIN 的比例",
        SUMMARY_DIMENSION,
        ["gauge", "table", "pie", "bar"],
        "gauge",
        "单一比率首选 gauge；需明细用表格；占整体比例可用饼图",
        "formula 或预计算 repeat_rate", "Carlog用户复访率",
    ),
    _spec(
        "cohort_retention", "队列留存",
        "按首次使用日期分队列，观测 D+1/D+3/D+7 等留存率",
        COHORT_DATE_DIMENSION,
        ["line", "multi_line", "area", "heatmap", "table"],
        "line",
        "留存曲线用折线/面积；队列×天数矩阵用热力图；明细用表格",
        "retention_rate + retained_users", "Carlog按首次使用日的7日留存",
        "sub_dimension=留存天数; cohort_retention_days=[1,3,7,14,30]",
    ),
    _spec(
        "funnel", "漏斗转化",
        "多事件按顺序转化，统计每步到达车辆数及转化率",
        FUNNEL_STEP_DIMENSION,
        ["funnel_chart", "horizontal_bar", "bar", "table"],
        "funnel_chart",
        "漏斗首选 funnel_chart；步骤对比可用横向柱；精确数值用表格",
        "user_count + conversion_rate", "Carlog从进入到完成的转化漏斗",
        "comparison_events: 有序事件列表(≥2)",
    ),
    _spec(
        "event_comparison", "多事件对比",
        "多个事件在同一时间轴或柱状图上对比 PV/UV",
        "date 或 event",
        ["multi_line", "line", "stacked_bar", "bar", "horizontal_bar", "table"],
        "multi_line",
        "时间对比用多折线；同一时点事件对比用柱图；构成用堆叠柱",
        "count 或 nunique", "Carlog进入与Carlog退出每日对比",
        "comparison_events: 事件列表; sub_dimension=event(时间对比时)",
    ),
    _spec(
        "active_users", "活跃用户 DAU/WAU/MAU",
        "统计周期末的日活、近7日周活、近30日月活",
        ACTIVE_USER_DIMENSION,
        ["bar", "horizontal_bar", "table", "line", "gauge"],
        "bar",
        "三指标对比用柱图；强调某一指标可用 gauge；明细用表格",
        "dau/wau/mau 或 nunique", "Carlog最近DAU和MAU",
    ),
    _spec(
        "growth_rate", "增长率",
        "基于日粒度时间序列计算环比增长率",
        "date",
        ["line", "bar", "area", "table"],
        "line",
        "增长率趋势用折线；正负波动强调用柱图（正负分色）",
        "growth_rate (formula)", "Carlog UV近7日环比增长率",
    ),
    _spec(
        "stickiness", "粘性 DAU/MAU",
        "日活/月活比值，衡量用户粘性",
        SUMMARY_DIMENSION,
        ["gauge", "table", "bar"],
        "gauge",
        "单一粘性比率首选 gauge；附带 DAU/MAU 明细用表格",
        "stickiness (formula)", "Carlog用户粘性",
    ),
    _spec(
        "percentile_stats", "使用次数分位数",
        "每 VIN 使用次数的 P50/P75/P90/P99",
        PERCENTILE_DIMENSION,
        ["bar", "horizontal_bar", "line", "table"],
        "bar",
        "分位点对比用柱图；展示分布形态可用折线连接各分位",
        "usage_count", "Carlog使用次数P50和P90",
    ),
    _spec(
        "heatmap_time", "时间热力",
        "日期 × 时段 二维交叉，发现使用热力分布",
        "date",
        ["heatmap", "table", "stacked_bar", "bar"],
        "heatmap",
        "二维交叉首选热力图；无法渲染时降级为表格或堆叠柱",
        "count", "Carlog每日各时段触发热力",
        f"sub_dimension={HOUR_OF_DAY_DIMENSION}",
    ),
    _spec(
        "first_touch_trend", "新增用户趋势",
        "按 VIN 首次触发日期统计每日新增用户数",
        "date",
        ["area", "line", "bar", "table"],
        "area",
        "新增趋势强调体量用面积图；简洁趋势用折线",
        "nunique(vin_code), id=new_users", "Carlog每日新增用户趋势",
    ),
]

ANALYSIS_TYPE_IDS: set[str] = {spec["id"] for spec in ANALYSIS_CATALOG}
ANALYSIS_SPEC_BY_ID: dict[str, AnalysisTypeSpec] = {spec["id"]: spec for spec in ANALYSIS_CATALOG}


def get_analysis_spec(analysis_type: str) -> AnalysisTypeSpec | None:
    return ANALYSIS_SPEC_BY_ID.get(analysis_type)


def get_allowed_chart_types(analysis_type: str) -> list[str]:
    spec = get_analysis_spec(analysis_type)
    return list(spec["chart_types"]) if spec else list(CHART_TYPE_IDS)


def build_chart_catalog_prompt() -> str:
    """生成图表类型全局说明，供 LLM 选型参考。"""
    lines = ["## 可用图表类型（visualization.chart_type 只能选下列之一）"]
    for chart_id, meta in CHART_TYPE_CATALOG.items():
        lines.append(
            f"- **{chart_id}**（{meta['name']}）：{meta['use_when']}"
        )
    lines.append(
        "\n**选型原则**：必须从当前 analysis_type 的「可选图表」中选择；"
        "优先选「默认图表」除非用户明确偏好其他形式（如「看占比」→ pie，「看排名」→ horizontal_bar）。"
    )
    return "\n".join(lines)


def build_analysis_catalog_prompt() -> str:
    """生成注入 LLM system prompt 的分析类型说明。"""
    lines = ["## 可用分析类型（analysis_type 必填，只能选下列之一）"]
    for spec in ANALYSIS_CATALOG:
        extra = f"\n  - 额外字段: {spec['extra_fields']}" if spec.get("extra_fields") else ""
        charts = ", ".join(spec["chart_types"])
        lines.append(
            f"- **{spec['id']}**（{spec['name']}）：{spec['description']}\n"
            f"  - dimension: {spec['dimension']}\n"
            f"  - 可选图表: {charts}\n"
            f"  - 默认图表: {spec['default_chart']}\n"
            f"  - 选型提示: {spec['chart_guide']}\n"
            f"  - 指标: {spec['metric_hint']}\n"
            f"  - 示例: {spec['example_query']}{extra}"
        )
    lines.append(
        "\n**重要规则**：\n"
        "1. analysis_type 决定后端聚合，不要编造 CSV 中不存在的 dimension\n"
        "2. visualization.chart_type 必须属于该 analysis_type 的「可选图表」列表\n"
        "3. 留存/频次 → usage_retention / usage_distribution，dimension=使用次数分组\n"
        "4. 漏斗/多事件对比 → 必须填 comparison_events（有序事件名列表）\n"
        "5. Top N → top_n_ranking + top_n 字段\n"
        "6. 队列留存 → cohort_retention + cohort_retention_days\n"
        "7. 时段规律 → period_pattern + period_unit(hour/weekday)"
    )
    return "\n".join(lines)


def normalize_visualization_chart(plan: AnalysisPlan) -> AnalysisPlan:
    """校验并校正 chart_type，不在允许范围时回退到默认图表。"""
    analysis_type = plan.analysis_type or infer_analysis_type(plan)
    spec = get_analysis_spec(analysis_type)
    if not spec:
        return plan

    allowed = set(spec["chart_types"])
    chart_type = plan.visualization.chart_type
    if chart_type in allowed:
        return plan

    default_chart = spec["default_chart"]
    visualization = plan.visualization.model_copy(
        update={
            "chart_type": default_chart,
            "reasoning": (
                f"{plan.visualization.reasoning} "
                f"(原选 {chart_type} 不在 {analysis_type} 允许范围，已校正为 {default_chart})"
            ),
        }
    )
    return plan.model_copy(update={"visualization": visualization})


def is_usage_bucket_dimension(dimension: str) -> bool:
    return bool(_USAGE_BUCKET_PATTERN.search(dimension)) or dimension == USAGE_BUCKET_DIMENSION


def is_derived_dimension(dimension: str) -> bool:
    return dimension in DERIVED_DIMENSIONS


def is_time_dimension(dimension: str) -> bool:
    return dimension in _TIME_DIMENSIONS or bool(
        re.search(r"date|time|timestamp|日期|时间", dimension, re.I)
    )


def _wants_retention_only(plan: AnalysisPlan) -> bool:
    text = f"{plan.statistical_caliber.description} {' '.join(m.name for m in plan.metrics)}"
    tokens = ("留存", "1次", "2次", "一次", "两次", "retention")
    if any(token in text for token in tokens):
        return True
    return any(
        "1" in f"{m.id}{m.name}" or "2" in f"{m.id}{m.name}" for m in plan.metrics
    )


def _infer_period_unit(plan: AnalysisPlan) -> str:
    if plan.period_unit in ("hour", "weekday"):
        return plan.period_unit
    dim = plan.dimension
    if _WEEKDAY_PATTERN.search(dim) or "weekday" in dim.lower():
        return "weekday"
    return "hour"


def infer_analysis_type(plan: AnalysisPlan) -> AnalysisType:
    """从计划中推断分析类型（兼容旧计划无 analysis_type 字段）。"""
    if plan.analysis_type and plan.analysis_type in ANALYSIS_TYPE_IDS:
        return plan.analysis_type  # type: ignore[return-value]

    desc = plan.statistical_caliber.description
    combined = f"{desc} {plan.dimension} {' '.join(m.name for m in plan.metrics)}"

    if plan.comparison_events and len(plan.comparison_events) >= 2:
        if _FUNNEL_PATTERN.search(combined):
            return "funnel"
        return "event_comparison"
    if is_usage_bucket_dimension(plan.dimension):
        return "usage_retention" if _wants_retention_only(plan) else "usage_distribution"
    if _ACTIVE_DAYS_PATTERN.search(combined):
        return "active_days_distribution"
    if _NEW_USER_PATTERN.search(combined):
        return "new_vs_returning"
    if _COHORT_PATTERN.search(combined) and "留存" in combined:
        return "cohort_retention"
    if _TOP_N_PATTERN.search(combined):
        return "top_n_ranking"
    if _GROWTH_PATTERN.search(combined):
        return "growth_rate"
    if _PERCENTILE_PATTERN.search(combined):
        return "percentile_stats"
    if _HEATMAP_PATTERN.search(combined):
        return "heatmap_time"
    if _DAU_PATTERN.search(combined):
        return "active_users"
    if _STICKINESS_PATTERN.search(combined):
        return "stickiness"
    if _FIRST_TOUCH_PATTERN.search(combined):
        return "first_touch_trend"
    if _HOUR_PATTERN.search(plan.dimension) or _WEEKDAY_PATTERN.search(plan.dimension):
        return "period_pattern"
    if "复访" in combined or "repeat" in combined.lower():
        return "repeat_rate"
    if plan.sub_dimension:
        return "cross_dimension"
    if any(m.type == "formula" for m in plan.metrics):
        return "penetration"
    if is_time_dimension(plan.dimension):
        return "time_series"
    if plan.dimension == SUMMARY_DIMENSION:
        return "summary_kpi"
    return "dimension_breakdown"


def validate_analysis_type(analysis_type: str) -> None:
    if analysis_type not in ANALYSIS_TYPE_IDS:
        allowed = ", ".join(sorted(ANALYSIS_TYPE_IDS))
        raise ValueError(f"analysis_type 必须是以下之一: {allowed}")


def normalize_plan_for_analysis(plan: AnalysisPlan) -> AnalysisPlan:
    """根据 analysis_type 规范化 dimension 与辅助字段。"""
    analysis_type = infer_analysis_type(plan)
    updates: dict = {"analysis_type": analysis_type}

    dimension_map = {
        "usage_retention": USAGE_BUCKET_DIMENSION,
        "usage_distribution": USAGE_BUCKET_DIMENSION,
        "active_days_distribution": ACTIVE_DAYS_BUCKET_DIMENSION,
        "new_vs_returning": USER_TYPE_DIMENSION,
        "repeat_rate": SUMMARY_DIMENSION,
        "stickiness": SUMMARY_DIMENSION,
        "percentile_stats": PERCENTILE_DIMENSION,
        "active_users": ACTIVE_USER_DIMENSION,
        "funnel": FUNNEL_STEP_DIMENSION,
        "summary_kpi": SUMMARY_DIMENSION,
    }
    if analysis_type in dimension_map:
        updates["dimension"] = dimension_map[analysis_type]

    if analysis_type == "time_series" and not is_time_dimension(plan.dimension):
        updates["dimension"] = "date"
    elif analysis_type == "growth_rate":
        updates["dimension"] = "date"
    elif analysis_type == "first_touch_trend":
        updates["dimension"] = "date"
    elif analysis_type == "cohort_retention":
        updates["dimension"] = COHORT_DATE_DIMENSION
        if not plan.sub_dimension:
            updates["sub_dimension"] = RETENTION_DAY_DIMENSION
    elif analysis_type == "period_pattern":
        unit = _infer_period_unit(plan)
        updates["period_unit"] = unit
        updates["dimension"] = (
            DAY_OF_WEEK_DIMENSION if unit == "weekday" else HOUR_OF_DAY_DIMENSION
        )
    elif analysis_type == "heatmap_time":
        updates["dimension"] = "date"
        if not plan.sub_dimension:
            updates["sub_dimension"] = HOUR_OF_DAY_DIMENSION
    elif analysis_type == "event_comparison":
        if is_time_dimension(plan.dimension):
            updates["dimension"] = "date"
            if not plan.sub_dimension:
                updates["sub_dimension"] = EVENT_NAME_DIMENSION
        else:
            updates["dimension"] = EVENT_NAME_DIMENSION

    if analysis_type in ("funnel", "event_comparison") and not plan.comparison_events:
        updates["comparison_events"] = [plan.matched_event]

    if analysis_type == "cohort_retention" and not plan.cohort_retention_days:
        updates["cohort_retention_days"] = [1, 3, 7, 14, 30]

    if analysis_type == "top_n_ranking" and not plan.top_n:
        updates["top_n"] = 10

    plan = plan.model_copy(update=updates)
    return normalize_visualization_chart(plan)


def uses_derived_dimension(analysis_type: str) -> bool:
    return analysis_type in {
        "usage_retention",
        "usage_distribution",
        "active_days_distribution",
        "summary_kpi",
        "new_vs_returning",
        "repeat_rate",
        "cohort_retention",
        "funnel",
        "active_users",
        "stickiness",
        "percentile_stats",
        "period_pattern",
        "growth_rate",
        "first_touch_trend",
        "heatmap_time",
    }


def is_multi_event_analysis(analysis_type: str) -> bool:
    return analysis_type in ("funnel", "event_comparison")


def needs_full_dataset(analysis_type: str) -> bool:
    """需要未做时间过滤的全量数据（用于计算首次出现等）。"""
    return analysis_type in ("new_vs_returning", "first_touch_trend", "cohort_retention")
