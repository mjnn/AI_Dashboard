"""Agent 分析规划阶段 Schema（意图 → 字典 → 故事 → 可视化 ↔ 数据校验）。"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from schemas.analysis import MetricDef, TimeRange

ScopeMode = Literal["single_event", "event_list", "module", "comprehensive"]


class AgentIntent(BaseModel):
    goal: str = Field(description="用户分析目标的一句话概括")
    intent_confidence: Literal["high", "medium", "low"] = "medium"
    exploratory_mode: bool = False
    user_focus: Optional[str] = Field(
        default=None, description="关注点，如漏斗/趋势/对比/留存"
    )
    intent_type: Optional[str] = Field(
        default=None,
        description="分析类型，须为 analysis 注册表中的 analysis_type，如 usage_retention、funnel、time_series",
    )
    scope_mode: Optional[ScopeMode] = Field(
        default=None,
        description="事件范围：single_event 单事件 | event_list 明确列表 | module 整模块 | comprehensive 全面综合",
    )


class DictionaryLookup(BaseModel):
    matched_event: str
    matched_module: str
    match_confidence: Literal["high", "medium", "low"] = "medium"
    related_events: List[str] = Field(default_factory=list)
    csv_event_filter: List[str] = Field(default_factory=list)
    comparison_events: Optional[List[str]] = None
    mapping_note: Optional[str] = None


class AgentStory(BaseModel):
    headline: str = Field(min_length=2, max_length=80)
    narrative: str = Field(min_length=8, max_length=600)
    takeaway: Optional[str] = Field(default=None, max_length=200)


class DataRequirementSpec(BaseModel):
    """单次可视化所需的数据规格（由 LLM 提出，由代码校验）。"""

    csv_event_filter: List[str] = Field(default_factory=list)
    comparison_events: Optional[List[str]] = None
    dimension: str = "date"
    sub_dimension: Optional[str] = None
    metrics: List[MetricDef] = Field(min_length=1)
    filters: Dict[str, str] = Field(default_factory=dict)
    time_range: TimeRange = Field(
        default_factory=lambda: TimeRange(type="last_n_days", value=30)
    )
    top_n: Optional[int] = None
    cohort_retention_days: Optional[List[int]] = None
    period_unit: Optional[Literal["hour", "weekday"]] = None


class VisualizationProposal(BaseModel):
    panel_id: str = "primary"
    analysis_type: str
    chart_type: str
    layout: Literal["single", "dual", "grid"] = "single"
    title: str
    reasoning: str
    data_requirements: DataRequirementSpec


class DataFeasibilityCheck(BaseModel):
    panel_id: str
    ready: bool
    filtered_rows: int = 0
    preview_rows: int = 0
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class AgentRoundTrace(BaseModel):
    round: int
    proposals: List[VisualizationProposal]
    feedback: List[DataFeasibilityCheck]


class AgentContextBundle(BaseModel):
    intent: AgentIntent
    dictionary: DictionaryLookup
    story: AgentStory


class AgentExecutionTrace(BaseModel):
    """完整 Agent 执行轨迹，供调试与前端可选展示。"""

    phases: List[str] = Field(
        default_factory=lambda: [
            "intent",
            "dictionary",
            "story",
            "visualization_loop",
            "chart_build",
        ]
    )
    context: AgentContextBundle
    rounds: List[AgentRoundTrace] = Field(default_factory=list)
    final_panel_id: Optional[str] = None
    converged: bool = False
    total_rounds: int = 0
    cache_hit: bool = False
    cache_signature: Optional[str] = None
    phases_skipped: List[str] = Field(default_factory=list)


class AgentContextPayload(BaseModel):
    """LLM 第一阶段输出：意图 + 字典 + 故事。"""

    intent: AgentIntent
    dictionary: DictionaryLookup
    story: AgentStory


class AgentVisualizationPayload(BaseModel):
    """LLM 可视化规划阶段输出。"""

    story_refined: Optional[str] = None
    visualizations: List[VisualizationProposal] = Field(min_length=1)


class AgentRevisionPayload(BaseModel):
    """LLM 根据代码反馈修订后的输出。"""

    revision_summary: str = ""
    visualizations: List[VisualizationProposal] = Field(min_length=1)
