/** 指标类型 */
export type MetricType = "count" | "nunique" | "formula";

/** 指标定义 */
export interface MetricDef {
  /** 指标唯一 ID，如 "pv" / "uv_vin" / "penetration" */
  id: string;
  /** 显示名，如 "触发次数" */
  name: string;
  /** 指标类型：count 计数 / nunique 去重计数 / formula 复合指标 */
  type: MetricType;
  /** nunique 时的去重字段，如 "vin_code" */
  field?: string;
  /** formula 时的表达式，如 "count / unique_vin" */
  formula?: string;
  /** 公式依赖的基础指标 ID 列表 */
  formula_components?: string[];
}

/** 统计口径说明 */
export interface StatisticalCaliber {
  /** 去重方式，如 "按VIN去重" / "无去重" / "按用户去重" */
  dedup_method: string;
  /** 时间聚合粒度，如 "daily" / "hourly" / "weekly" */
  time_granularity: string;
  /** LLM 生成的自然语言口径描述 */
  description: string;
}

/** 图表类型 */
export type ChartType =
  | "line"
  | "area"
  | "multi_line"
  | "dual_axis"
  | "bar"
  | "horizontal_bar"
  | "stacked_bar"
  | "pie"
  | "table"
  | "heatmap"
  | "gauge"
  | "funnel_chart";

/** 图表布局 */
export type ChartLayout = "single" | "dual" | "grid";

/** 可视化选型 */
export interface VisualizationDef {
  /** 图表类型 */
  chart_type: ChartType;
  /** 图表布局 */
  layout: ChartLayout;
  /** LLM 解释选择该图表的理由 */
  reasoning: string;
}

/** 时间范围类型 */
export type TimeRangeType = "last_n_days" | "date_range";

/** 时间范围 */
export interface TimeRange {
  /** 时间范围类型 */
  type: TimeRangeType;
  /** last_n_days 时的天数 */
  value?: number;
  /** date_range 时的起始日期 */
  start?: string;
  /** date_range 时的结束日期 */
  end?: string;
}

/** 匹配置信度 */
export type MatchConfidence = "high" | "medium" | "low";

/** 分析类型（后端注册表枚举，共 21 种） */
export type AnalysisType =
  | "time_series"
  | "dimension_breakdown"
  | "top_n_ranking"
  | "usage_retention"
  | "usage_distribution"
  | "active_days_distribution"
  | "penetration"
  | "cross_dimension"
  | "summary_kpi"
  | "period_pattern"
  | "new_vs_returning"
  | "repeat_rate"
  | "cohort_retention"
  | "funnel"
  | "event_comparison"
  | "active_users"
  | "growth_rate"
  | "stickiness"
  | "percentile_stats"
  | "heatmap_time"
  | "first_touch_trend";

/** LLM 生成的分析计划 */
export interface AnalysisPlan {
  /** 分析类型，决定后端聚合方式 */
  analysis_type?: AnalysisType;
  /** 字典中的事件名 */
  matched_event: string;
  /** 所属功能模块 */
  matched_module: string;
  /** 事件匹配置信度 */
  match_confidence: MatchConfidence;
  /** 需要计算的指标列表 */
  metrics: MetricDef[];
  /** 统计口径 */
  statistical_caliber: StatisticalCaliber;
  /** 可视化选型 */
  visualization: VisualizationDef;
  /** 主分析维度，如 "date" */
  dimension: string;
  /** 次级维度（对比分析时），如 "vehicle_model" */
  sub_dimension?: string;
  /** 过滤条件，如 {"vin_code": "LSV..."} */
  filters: Record<string, string>;
  /** 时间范围 */
  time_range: TimeRange;
  /** 多事件对比/漏斗步骤 */
  comparison_events?: string[];
  /** Top N 排名 */
  top_n?: number;
  /** 队列留存观测天数 */
  cohort_retention_days?: number[];
  /** 时段规律：hour / weekday */
  period_unit?: "hour" | "weekday";
  /** 分析意图置信度 */
  intent_confidence?: MatchConfidence;
  /** 强制探索性全量分析 */
  exploratory_mode?: boolean;
  /** 数据池 CSV event 过滤范围 */
  csv_event_filter?: string[];
  /** 多事件分析范围展示名 */
  scope_label?: string;
}

/** 用户选择的分析模式（请求参数） */
export type AnalysisModePreference = "auto" | "precise" | "exploratory";

/** 分析请求 */
export interface AnalyzeRequest {
  /** 用户自然语言分析问题 */
  query: string;
  /** 分析模式：auto 智能 / precise 精准 / exploratory 探索 */
  analysis_mode?: AnalysisModePreference;
}

/** 面板布局 */
export type PanelLayout = "kpi" | "wide" | "half" | "compact";

/** 看板区块布局 */
export type SectionLayout =
  | "kpi_grid"
  | "wide_grid"
  | "half_grid"
  | "compact_grid"
  | "single";

/** LLM 单图叙事 */
export interface PanelNarration {
  panel_id: string;
  title: string;
  subtitle?: string;
  tag?: string;
}

/** LLM 看板主题区块 */
export interface DashboardSection {
  id: string;
  title: string;
  subtitle: string;
  highlight?: string;
  panel_ids: string[];
  layout: SectionLayout;
}

/** LLM 看板整体叙事 */
export interface DashboardPresentation {
  headline: string;
  summary: string;
  sections: DashboardSection[];
  panels: PanelNarration[];
}

/** 响应模式 */
export type AnalysisMode = "single" | "exploratory" | "comprehensive";

/** 探索性分析面板 */
export interface AnalysisPanel {
  panel_id: string;
  analysis_type: string;
  name: string;
  layout: PanelLayout;
  plan: AnalysisPlan;
  execution: ExecutionSummary;
  chart_config: ChartConfig;
}

/** 执行状态 */
export type ExecutionStatus = "success" | "partial" | "failed";

/** 数据处理执行摘要 */
export interface ExecutionSummary {
  /** 执行状态 */
  status: ExecutionStatus;
  /** 本次 CSV 中不可用的维度字段 */
  unavailable_dimensions: string[];
  /** CSV 总行数 */
  total_rows: number;
  /** 过滤后行数 */
  filtered_rows: number;
  /** 执行耗时（毫秒） */
  execution_time_ms: number;
}

/** 单图面板结构化统计口径 */
export interface PanelCaliberDetail {
  description: string;
  dedup_method: string;
  time_granularity: string;
  events: string[];
  formulas: string[];
  /** 衍生维度分组规则，如新老用户如何划分 */
  grouping_rules?: string[];
  /** 图表如何绘制：横纵轴、系列、阅读方式 */
  chart_layout?: string[];
}

/** ECharts 图表配置 */
export interface ChartConfig {
  /** 图表类型 */
  chart_type: string;
  /** 图表标题 */
  title: string;
  /** X 轴数据字段键名 */
  x_axis_key: string;
  /** Y 轴数据字段键名列表 */
  y_axis_keys: string[];
  /** 次级轴字段（热力图 Y 轴等） */
  sub_axis_key?: string;
  /** 数值字段（热力图/仪表盘） */
  value_key?: string;
  /** 系列配置列表 */
  series: Record<string, unknown>[];
  /** 聚合后的图表数据 */
  data: Record<string, unknown>[];
  /** 口径说明文本列表，供前端展示 */
  calibers: string[];
  /** 结构化口径：统计说明、使用事件、计算公式 */
  caliber_detail?: PanelCaliberDetail;
}

/** 分析 API 响应 */
export interface AnalysisResponse {
  /** single 单图 / exploratory 多面板 */
  mode?: AnalysisMode;
  /** LLM 原始分析计划（可审计） */
  plan: AnalysisPlan;
  /** 数据处理执行摘要 */
  execution: ExecutionSummary;
  /** ECharts 图表配置 */
  chart_config: ChartConfig;
  /** 探索性分析面板列表 */
  panels?: AnalysisPanel[];
  /** 进入探索模式的原因 */
  exploratory_reason?: string;
  /** 面板数量 */
  panel_count?: number;
  /** LLM 看板分类与生动文案 */
  presentation?: DashboardPresentation;
  /** 本次纳入的 CSV event 列表（多事件综合） */
  scope_events?: string[];
  /** LLM 事件聚类项 */
  analysis_clusters?: AnalysisClusterSummary[];
  /** 场景深度挖掘建议 */
  depth_insights?: string[];
}

export interface AnalysisClusterSummary {
  id: string;
  name: string;
  rationale: string;
  csv_events: string[];
  analysis_angles: string[];
  is_primary: boolean;
}

/** 模块事件分组 */
export interface EventModule {
  name: string;
  events: string[];
}

/** 可用事件列表响应 */
export interface EventsListResponse {
  /** 按模块分组的事件列表 */
  modules: EventModule[];
  /** 事件总数 */
  total_events: number;
}

/** 单条分析推荐 */
export interface AnalysisRecommendation {
  /** 简短标签 */
  title: string;
  /** 可直接提交的自然语言问题 */
  query: string;
  /** 建议的分析模式 */
  analysis_mode: AnalysisModePreference;
  /** 推荐理由 */
  reason: string;
  /** 对应的 analysis_type */
  analysis_type?: string;
}

/** CSV 数据画像摘要 */
export interface DataSummary {
  columns: string[];
  total_rows: number;
  date_range?: {
    start: string;
    end: string;
    span_days: number;
  };
  events?: { name: string; count: number }[];
  unique_vins?: number;
  feasible_analysis_types?: string[];
}

/** LLM 分析推荐响应 */
export interface RecommendationsResponse {
  data_summary: DataSummary;
  recommendations: AnalysisRecommendation[];
  source: "llm" | "fallback";
}

/** CSV 文件信息 */
export interface CsvFileInfo {
  filename: string;
  size_bytes: number;
  modified_at: number;
}

/** CSV 数据目录文件列表 */
export interface CsvFilesResponse {
  data_dir: string;
  default_filename?: string;
  files: CsvFileInfo[];
  total: number;
}

/** CSV 上传响应 */
export interface CsvUploadResponse {
  filename: string;
  size_bytes: number;
  message: string;
  pool: CsvFilesResponse;
}

/** 字典树事件摘要 */
export interface DictionaryEventSummary {
  name: string;
  data_id: string;
  condition: string;
}

/** 字典模块节点 */
export interface DictionaryModuleNode {
  name: string;
  events: DictionaryEventSummary[];
}

/** 字典树响应 */
export interface DictionaryTreeResponse {
  source: string;
  description: string;
  modules: DictionaryModuleNode[];
  total_events: number;
}

/** 事件属性 */
export interface EventAttributeDesc {
  code?: number;
  label?: string;
}

export interface EventAttribute {
  事件的属性: string;
  属性中文说明?: string;
  属性值的描述?: string | EventAttributeDesc[] | null;
}

/** 事件详情 */
export interface DictionaryEventDetail {
  module: string;
  event: Record<string, unknown> & {
    事件?: string;
    事件触发条件?: string;
    事件Data_ID?: string;
    属性列表?: EventAttribute[];
  };
}

/** 事件更新请求 */
export interface DictionaryEventUpdate {
  事件触发条件?: string;
  事件Data_ID?: string;
  属性列表?: EventAttribute[];
}

/** 事件更新响应 */
export interface DictionaryEventUpdateResponse {
  event_name: string;
  message: string;
  event: DictionaryEventDetail["event"];
  total_events: number;
}

/** label 匹配统计 */
export interface DictionaryLabelStat {
  label: string;
  row_count: number;
  in_pool: boolean;
}

/** 字典测试请求 */
export interface DictionaryTestRequest {
  event_name: string;
  csv_labels?: string[];
}

/** 字典测试响应 */
export interface DictionaryTestResponse {
  event_name: string;
  event_column?: string | null;
  csv_labels_tested: string[];
  saved_csv_labels: string[];
  label_stats: DictionaryLabelStat[];
  total_matched_rows: number;
  pool_total_rows: number;
  distinct_csv_events: number;
  sample_rows: Record<string, unknown>[];
  suggested_csv_labels: string[];
}

export type DeepSeekModelId = "deepseek-v4-flash" | "deepseek-v4-pro";

export interface DeepSeekModelOption {
  id: DeepSeekModelId;
  label: string;
  selected: boolean;
}

export interface LlmSettingsResponse {
  model: DeepSeekModelId;
  available_models: DeepSeekModelOption[];
}

export interface LlmSettingsUpdate {
  model: DeepSeekModelId;
}
