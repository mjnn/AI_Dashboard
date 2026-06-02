"""分析请求与响应 Schema。"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class MetricDef(BaseModel):
    """指标定义。"""

    id: str = Field(description='指标唯一 ID，如 "pv" / "uv_vin" / "penetration"')
    name: str = Field(description='显示名，如 "触发次数"')
    type: Literal["count", "nunique", "formula"] = Field(
        description="指标类型：count 计数 / nunique 去重计数 / formula 复合指标"
    )
    field: Optional[str] = Field(
        default=None, description='nunique 时的去重字段，如 "vin_code"'
    )
    formula: Optional[str] = Field(
        default=None, description='formula 时的表达式，如 "count / unique_vin"'
    )
    formula_components: Optional[List[str]] = Field(
        default=None, description="公式依赖的基础指标 ID 列表"
    )


class StatisticalCaliber(BaseModel):
    """统计口径说明。"""

    dedup_method: str = Field(
        description='去重方式，如 "按VIN去重" / "无去重" / "按用户去重"'
    )
    time_granularity: str = Field(
        description='时间聚合粒度，如 "daily" / "hourly" / "weekly"'
    )
    description: str = Field(
        description="LLM 生成的自然语言口径描述，如统计每日独立 VIN 触发次数"
    )


class VisualizationDef(BaseModel):
    """可视化选型。"""

    chart_type: Literal[
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
    ] = Field(description="图表类型")
    layout: Literal["single", "dual", "grid"] = Field(description="图表布局")
    reasoning: str = Field(description="LLM 解释选择该图表的理由")


class TimeRange(BaseModel):
    """时间范围。"""

    type: Literal["last_n_days", "date_range"] = Field(description="时间范围类型")
    value: Optional[int] = Field(default=None, description="last_n_days 时的天数")
    start: Optional[str] = Field(default=None, description="date_range 时的起始日期")
    end: Optional[str] = Field(default=None, description="date_range 时的结束日期")


AnalysisTypeLiteral = Literal[
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


class AnalysisPlan(BaseModel):
    """LLM 生成的分析计划。"""

    analysis_type: Optional[AnalysisTypeLiteral] = Field(
        default=None,
        description="分析类型，决定后端聚合方式；LLM 必须从注册表枚举中选择",
    )
    matched_event: str = Field(description="字典中的事件名")
    matched_module: str = Field(description="所属功能模块")
    match_confidence: Literal["high", "medium", "low"] = Field(
        description="事件匹配置信度"
    )
    intent_confidence: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="分析意图置信度；low 时触发探索性全量分析",
    )
    exploratory_mode: bool = Field(
        default=False,
        description="是否强制探索性全量分析（LLM 或用户明确要求全面分析）",
    )
    metrics: List[MetricDef] = Field(min_length=1, description="需要计算的指标列表")
    statistical_caliber: StatisticalCaliber = Field(description="统计口径")
    visualization: VisualizationDef = Field(description="可视化选型")
    dimension: str = Field(description='主分析维度，如 "date"')
    sub_dimension: Optional[str] = Field(
        default=None, description='次级维度（对比分析时），如 "vehicle_model"'
    )
    filters: Dict[str, str] = Field(
        description='过滤条件，如 {"vin_code": "LSV..."}'
    )
    time_range: TimeRange = Field(description="时间范围")
    comparison_events: Optional[List[str]] = Field(
        default=None,
        description="多事件对比/漏斗步骤的有序事件名列表",
    )
    top_n: Optional[int] = Field(
        default=None, ge=1, le=100, description="Top N 排名时的 N 值"
    )
    cohort_retention_days: Optional[List[int]] = Field(
        default=None,
        description="队列留存观测天数，如 [1, 3, 7, 14, 30]",
    )
    period_unit: Optional[Literal["hour", "weekday"]] = Field(
        default=None,
        description="时段规律分析的单位：hour 按小时 / weekday 按星期",
    )
    csv_event_filter: Optional[List[str]] = Field(
        default=None,
        description="数据池 CSV event 列实际过滤取值；字典 matched_event 与 CSV 格式不一致时由 LLM 适配",
    )
    event_mapping_note: Optional[str] = Field(
        default=None,
        description="LLM 对字典事件名与 CSV event 取值的映射说明（可选）",
    )


class AnalyzeRequest(BaseModel):
    """分析请求。"""

    query: str = Field(min_length=1, max_length=500, description="用户自然语言分析问题")
    analysis_mode: Literal["auto", "precise", "exploratory"] = Field(
        default="auto",
        description="分析模式：auto 智能 / precise 精准单图 / exploratory 探索全量",
    )


class ExecutionSummary(BaseModel):
    """数据处理执行摘要。"""

    status: Literal["success", "partial", "failed"] = Field(description="执行状态")
    unavailable_dimensions: List[str] = Field(
        description="本次 CSV 中不可用的维度字段"
    )
    total_rows: int = Field(description="CSV 总行数")
    filtered_rows: int = Field(description="过滤后行数")
    execution_time_ms: int = Field(description="执行耗时（毫秒）")


class ChartConfig(BaseModel):
    """ECharts 图表配置。"""

    chart_type: str = Field(description="图表类型")
    title: str = Field(description="图表标题")
    x_axis_key: str = Field(description="X 轴数据字段键名")
    y_axis_keys: List[str] = Field(description="Y 轴数据字段键名列表")
    sub_axis_key: Optional[str] = Field(
        default=None, description="次级轴字段键名（热力图 Y 轴等）"
    )
    value_key: Optional[str] = Field(
        default=None, description="热力图/仪表盘数值字段键名"
    )
    series: List[dict] = Field(
        description='系列配置列表，如 [{"key": "pv", "name": "触发次数", "type": "line"}]'
    )
    data: List[dict] = Field(description="聚合后的图表数据")
    calibers: List[str] = Field(description="口径说明文本列表，供前端展示")


class AnalysisPanel(BaseModel):
    """探索性分析中的单个图表面板。"""

    panel_id: str = Field(description="面板唯一 ID")
    analysis_type: str = Field(description="分析类型")
    name: str = Field(description="面板显示名称")
    layout: Literal["kpi", "wide", "half", "compact"] = Field(
        description="前端布局提示：kpi / wide / half / compact"
    )
    plan: AnalysisPlan = Field(description="该面板的分析计划")
    execution: ExecutionSummary = Field(description="该面板的执行摘要")
    chart_config: ChartConfig = Field(description="该面板的图表配置")


class PanelNarration(BaseModel):
    """LLM 生成的单图叙事文案。"""

    panel_id: str = Field(description="对应面板 ID")
    title: str = Field(description="生动图表标题")
    subtitle: Optional[str] = Field(default=None, description="一句洞察补充")
    tag: Optional[str] = Field(default=None, description="短标签，如「核心 KPI」")


class DashboardSection(BaseModel):
    """LLM 划分的看板主题区块。"""

    id: str = Field(description="区块 ID")
    title: str = Field(description="区块标题，可中英混搭")
    subtitle: str = Field(description="区块说明")
    highlight: Optional[str] = Field(default=None, description="可选高亮洞察")
    panel_ids: List[str] = Field(description="该区块包含的面板 ID 列表")
    layout: Literal["kpi_grid", "wide_grid", "half_grid", "compact_grid", "single"] = (
        Field(default="half_grid", description="区块内布局方式")
    )


class DashboardPresentation(BaseModel):
    """LLM 生成的看板整体叙事结构。"""

    headline: str = Field(description="看板主标题")
    summary: str = Field(description="看板开篇总结，口语化")
    sections: List[DashboardSection] = Field(description="主题区块列表")
    panels: List[PanelNarration] = Field(description="各面板叙事文案")


class AnalysisResponse(BaseModel):
    """分析 API 响应。"""

    mode: Literal["single", "exploratory"] = Field(
        default="single",
        description="single 单图分析 / exploratory 探索性多面板",
    )
    plan: AnalysisPlan = Field(description="LLM 原始分析计划（可审计）")
    execution: ExecutionSummary = Field(description="数据处理执行摘要")
    chart_config: ChartConfig = Field(description="主图表配置（single 模式或 exploratory 首面板）")
    panels: Optional[List[AnalysisPanel]] = Field(
        default=None,
        description="探索性分析时的全部图表面板",
    )
    exploratory_reason: Optional[str] = Field(
        default=None,
        description="进入探索性模式的原因说明",
    )
    panel_count: int = Field(default=1, description="面板数量")
    presentation: Optional[DashboardPresentation] = Field(
        default=None,
        description="LLM 生成的看板分类与生动文案",
    )


class EventsListResponse(BaseModel):
    """可用事件列表响应。"""

    modules: List[dict] = Field(
        description='按模块分组的事件列表，如 [{"name": "蓝牙", "events": [...]}]'
    )
    total_events: int = Field(description="事件总数")


class AnalysisRecommendation(BaseModel):
    """单条分析推荐。"""

    title: str = Field(description="简短标签，供前端展示")
    query: str = Field(description="可直接提交的自然语言分析问题")
    analysis_mode: Literal["auto", "precise", "exploratory"] = Field(
        default="auto",
        description="建议的分析模式",
    )
    reason: str = Field(description="推荐理由，结合数据特征")
    analysis_type: Optional[str] = Field(
        default=None,
        description="对应的 analysis_type 枚举值",
    )


class RecommendationsResponse(BaseModel):
    """LLM 分析推荐响应。"""

    data_summary: dict = Field(description="CSV 数据画像摘要")
    recommendations: List[AnalysisRecommendation] = Field(
        description="分析推荐列表"
    )
    source: Literal["llm", "fallback"] = Field(
        description="推荐来源：llm 或规则兜底"
    )


class CsvFileInfo(BaseModel):
    """CSV 数据文件信息。"""

    filename: str = Field(description="文件名")
    size_bytes: int = Field(description="文件大小（字节）")
    modified_at: float = Field(description="最后修改时间（Unix 时间戳）")


class CsvFilesResponse(BaseModel):
    """CSV 数据目录文件列表。"""

    data_dir: str = Field(description="CSV 数据目录绝对路径")
    default_filename: Optional[str] = Field(
        default=None, description="未指定 csv_filename 时使用的默认文件"
    )
    files: List[CsvFileInfo] = Field(description="目录下全部 CSV 文件")
    total: int = Field(description="文件总数")


class AnalysisTypesResponse(BaseModel):
    """可用分析类型注册表响应。"""

    types: List[dict] = Field(description="分析类型目录")
    total: int = Field(description="分析类型总数")
    chart_types: List[dict] = Field(description="全局图表类型目录")
