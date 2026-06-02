"""看板叙事服务 — LLM 对图表面板分类并生成生动标题与洞察。"""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from schemas.analysis import (
    AnalysisPanel,
    AnalysisPlan,
    ChartConfig,
    DashboardPresentation,
    DashboardSection,
    PanelNarration,
)
from services.analysis_registry import ANALYSIS_SPEC_BY_ID
from services.locale import locale_instruction
from services.llm_planner import (
    AnalysisPlanError,
    LLMApiError,
    MissingApiKeyError,
    _create_client,
    _parse_llm_json,
)
from services.llm_settings import get_deepseek_model

SectionLayout = Literal["kpi_grid", "wide_grid", "half_grid", "compact_grid", "single"]


class _PanelNarrationItem(BaseModel):
    panel_id: str
    title: str = Field(min_length=2, max_length=48)
    subtitle: Optional[str] = Field(default=None, max_length=120)
    tag: Optional[str] = Field(default=None, max_length=16)


class _SectionItem(BaseModel):
    id: str
    title: str = Field(min_length=2, max_length=40)
    subtitle: str = Field(min_length=4, max_length=160)
    highlight: Optional[str] = Field(default=None, max_length=80)
    panel_ids: List[str] = Field(min_length=1)
    layout: SectionLayout = "half_grid"


class _PresentationPayload(BaseModel):
    headline: str = Field(min_length=4, max_length=60)
    summary: str = Field(min_length=8, max_length=240)
    sections: List[_SectionItem] = Field(min_length=1, max_length=8)
    panels: List[_PanelNarrationItem] = Field(min_length=1)


def _numeric_values(data: list[dict], key: str) -> list[float]:
    values: list[float] = []
    for row in data:
        raw = row.get(key)
        if raw is None:
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            continue
    return values


def _summarize_chart_data(config: ChartConfig) -> dict[str, Any]:
    """从图表数据提取关键数字，供 LLM 写标题时引用。"""
    if not config.data:
        return {"empty": True}

    summary: dict[str, Any] = {"row_count": len(config.data)}
    x_key = config.x_axis_key
    if x_key and config.data:
        summary["x_samples"] = [
            str(row.get(x_key, "")) for row in config.data[:3]
        ] + ([str(config.data[-1].get(x_key, ""))] if len(config.data) > 3 else [])

    metric_keys = config.y_axis_keys or (
        [config.value_key] if config.value_key else []
    )
    metrics: dict[str, Any] = {}
    for key in metric_keys:
        if not key:
            continue
        nums = _numeric_values(config.data, key)
        if not nums:
            continue
        metrics[key] = {
            "min": round(min(nums), 2),
            "max": round(max(nums), 2),
            "latest": round(nums[-1], 2),
            "avg": round(sum(nums) / len(nums), 2),
        }
    if metrics:
        summary["metrics"] = metrics

    if config.chart_type == "gauge" and config.data:
        summary["gauge_value"] = config.data[0]

    return summary


def _summarize_panel(panel: AnalysisPanel) -> dict[str, Any]:
    spec = ANALYSIS_SPEC_BY_ID.get(panel.analysis_type, {})
    return {
        "panel_id": panel.panel_id,
        "analysis_type": panel.analysis_type,
        "analysis_name": spec.get("name", panel.analysis_type),
        "chart_type": panel.plan.visualization.chart_type,
        "layout_hint": panel.layout,
        "current_title": panel.name,
        "event": panel.plan.matched_event,
        "data_stats": _summarize_chart_data(panel.chart_config),
    }


def _build_narrator_prompt(
    panels: List[AnalysisPanel],
    plan: AnalysisPlan,
    query: str,
    *,
    scope_event_count: int = 1,
    depth_insights: Optional[List[str]] = None,
    analysis_angles: Optional[List[str]] = None,
) -> str:
    import json

    panel_briefs = [_summarize_panel(p) for p in panels]
    panel_json = json.dumps(panel_briefs, ensure_ascii=False, indent=2)
    scope_line = plan.scope_label or plan.matched_event
    if scope_event_count > 1:
        scope_line = f"{scope_line}（综合 {scope_event_count} 个相关事件）"

    angles_block = ""
    if analysis_angles:
        angles_block = "\n## 建议深挖角度\n" + "\n".join(
            f"- {a}" for a in analysis_angles[:6]
        )
    insights_block = ""
    if depth_insights:
        insights_block = "\n## 场景深度洞察（请融入 summary 与 highlight）\n" + "\n".join(
            f"- {i}" for i in depth_insights[:6]
        )

    return f"""你是一位座舱埋点数据的「故事讲述者」。请根据下方真实分析结果，为看板生成分类结构与生动文案。

## 用户问题
{query}

## 分析范围
{scope_line}（{plan.matched_module}）
{angles_block}
{insights_block}

## 图表面板（含真实数据摘要）
{panel_json}

## 你的任务
1. **分类**：将面板归入 2~5 个主题区块（如「一眼看清大盘」「趋势里的起伏」「用户怎么用」「频次分布」），同一区块内的面板语义相近
2. **区块标题**：每个区块写 title（可中英混搭，如「趋势脉搏 / Trend Pulse」）和 subtitle（一句话说明这个区块讲什么）
3. **highlight**（可选）：若某区块有值得点醒的洞察，写一句短 highlight（≤30字，可带数据）
4. **图表标题**：为每个 panel_id 写 title —— 要**生动、有画面感、带洞察**，禁止机械套话
   - 好：「日触发量缓步爬坡，5 月中旬摸到小高峰」
   - 好：「近半数车主只来了一次，回访还有空间」
   - 坏：「时间序列分析-触发次数」
   - 坏：「usage_retention 柱状图」
5. **subtitle**：每个图表一句补充洞察（可引用数据中的 max/latest/avg）
6. **tag**（可选）：2~6 字标签，如「值得关注」「粘性预警」「核心 KPI」
7. **headline**：整个看板主标题（≤20字，有事件名）
8. **summary**：看板开篇 1~2 句总结，口语化、有温度，像给运营同事的简报
9. **layout**：每个 section 指定布局
   - kpi_grid：核心 KPI / gauge 类，3~4 个并排
   - wide_grid：趋势折线 /  cohort，1~2 列宽图
   - half_grid：行为分布 / 对比，2 列
   - compact_grid：3 个小图紧凑排列
   - single：仅 1 个面板

## 约束
- panel_ids 必须覆盖且仅覆盖上述全部 panel_id，不可遗漏或编造
- 每个 panel_id 在 panels 数组中恰好出现一次
- 文案用中文为主，可少量英文点缀；数字可引用 data_stats
- 只输出 JSON，格式如下：

{{
  "headline": "Carlog 21 天运营快照",
  "summary": "近三千辆车在这三周里敲开了 Carlog，日活像波浪一样起伏——下面按「大盘→趋势→行为」帮你拆开看。",
  "sections": [
    {{
      "id": "overview",
      "title": "一眼看清 / At a Glance",
      "subtitle": "PV、UV、粘性——三个数字先建立直觉",
      "highlight": "2876 辆车参与，平均每车用了 3.6 次",
      "panel_ids": ["summary_kpi-0"],
      "layout": "kpi_grid"
    }}
  ],
  "panels": [
    {{
      "panel_id": "summary_kpi-0",
      "title": "三周累计：一万次触达背后的体量感",
      "subtitle": "PV 与 UV 告诉你声量，粘性则透露回访意愿",
      "tag": "核心 KPI"
    }}
  ]
}}"""


def _validate_presentation(
    data: dict,
    raw_output: str,
    panel_ids: set[str],
) -> DashboardPresentation:
    try:
        payload = _PresentationPayload.model_validate(data)
    except ValidationError as exc:
        raise AnalysisPlanError(
            f"看板叙事校验失败: {exc}", raw_output=raw_output
        ) from exc

    narrated_ids = {item.panel_id for item in payload.panels}
    section_ids: set[str] = set()
    for section in payload.sections:
        section_ids.update(section.panel_ids)

    if narrated_ids != panel_ids:
        missing = panel_ids - narrated_ids
        extra = narrated_ids - panel_ids
        raise AnalysisPlanError(
            f"看板叙事 panel_id 不匹配: 缺失 {missing}, 多余 {extra}",
            raw_output=raw_output,
        )
    if section_ids != panel_ids:
        raise AnalysisPlanError(
            "看板叙事 sections 未完整覆盖全部 panel_id",
            raw_output=raw_output,
        )

    return DashboardPresentation(
        headline=payload.headline,
        summary=payload.summary,
        sections=[
            DashboardSection(
                id=s.id,
                title=s.title,
                subtitle=s.subtitle,
                highlight=s.highlight,
                panel_ids=s.panel_ids,
                layout=s.layout,
            )
            for s in payload.sections
        ],
        panels=[
            PanelNarration(
                panel_id=p.panel_id,
                title=p.title,
                subtitle=p.subtitle,
                tag=p.tag,
            )
            for p in payload.panels
        ],
    )


def _fallback_presentation(
    panels: List[AnalysisPanel],
    plan: AnalysisPlan,
) -> DashboardPresentation:
    """LLM 不可用时的规则兜底分类与标题。"""
    groups: dict[str, list[str]] = {
        "kpi": [],
        "wide": [],
        "half": [],
    }
    narrations: list[PanelNarration] = []

    vivid_titles = {
        "summary_kpi": "先抓大放小：核心 KPI 一屏读完",
        "active_users": "有多少车在「活跃」？",
        "stickiness": "粘性如何：来了还会再来吗",
        "repeat_rate": "复访率：老用户占比几何",
        "time_series": "日趋势：声量随时间如何起伏",
        "first_touch_trend": "新触达曲线：谁在陆续「第一次」",
        "growth_rate": "环比变化：涨跌幅一目了然",
        "usage_retention": "用几次才走：留存分桶画像",
        "usage_distribution": "频次分布：重度与轻度用户各占多少",
        "new_vs_returning": "新老用户：首次与回访的角力",
        "active_days_distribution": "活跃天数：用户「出勤」分布",
        "period_pattern": "时段规律：什么时候最爱用",
        "percentile_stats": "分位统计：头部与长尾差多远",
        "heatmap_time": "热力图：时间 × 行为的热度",
        "cohort_retention": "队列留存：不同批次谁留得更久",
        "dimension_breakdown": "维度拆解：各分组差异对比",
        "top_n_ranking": "Top 排行：谁排在最前面",
    }

    for panel in panels:
        layout = panel.layout
        if layout == "kpi":
            groups["kpi"].append(panel.panel_id)
        elif layout == "wide":
            groups["wide"].append(panel.panel_id)
        else:
            groups["half"].append(panel.panel_id)

        base = vivid_titles.get(
            panel.analysis_type,
            panel.name or panel.analysis_type,
        )
        narrations.append(
            PanelNarration(
                panel_id=panel.panel_id,
                title=base,
                subtitle=panel.plan.statistical_caliber.description[:80],
                tag="核心 KPI" if panel.layout == "kpi" else None,
            )
        )

    sections: list[DashboardSection] = []
    if groups["kpi"]:
        sections.append(
            DashboardSection(
                id="overview",
                title="一眼看清 / At a Glance",
                subtitle=f"{plan.matched_event} 核心指标速览",
                panel_ids=groups["kpi"],
                layout="kpi_grid",
            )
        )
    if groups["wide"]:
        sections.append(
            DashboardSection(
                id="trends",
                title="趋势脉搏 / Trend Pulse",
                subtitle="时间轴上的变化与起伏",
                panel_ids=groups["wide"],
                layout="wide_grid",
            )
        )
    if groups["half"]:
        sections.append(
            DashboardSection(
                id="behavior",
                title="用户行为 / User Behavior",
                subtitle="频次、留存与分布里的故事",
                panel_ids=groups["half"],
                layout="half_grid",
            )
        )

    if not sections and panels:
        sections.append(
            DashboardSection(
                id="main",
                title="分析结果",
                subtitle=plan.matched_event,
                panel_ids=[p.panel_id for p in panels],
                layout="single" if len(panels) == 1 else "half_grid",
            )
        )

    return DashboardPresentation(
        headline=f"{plan.scope_label or plan.matched_event} 数据洞察",
        summary=(
            f"基于 {plan.scope_label or plan.matched_event} 共 {len(panels)} 项分析，"
            "从多事件对比、趋势到行为分布层层拆开。"
        ),
        sections=sections,
        panels=narrations,
    )


def apply_presentation_to_panels(
    panels: List[AnalysisPanel],
    presentation: DashboardPresentation,
) -> List[AnalysisPanel]:
    """将 LLM 标题写回 panel 与 chart_config。"""
    narration_map = {n.panel_id: n for n in presentation.panels}
    updated: list[AnalysisPanel] = []

    for panel in panels:
        narration = narration_map.get(panel.panel_id)
        if not narration:
            updated.append(panel)
            continue

        new_chart = panel.chart_config.model_copy(
            update={"title": narration.title}
        )
        updated.append(
            panel.model_copy(
                update={
                    "name": narration.title,
                    "chart_config": new_chart,
                }
            )
        )
    return updated


def generate_dashboard_presentation(
    panels: List[AnalysisPanel],
    plan: AnalysisPlan,
    query: str,
    *,
    scope_event_count: int = 1,
    depth_insights: Optional[List[str]] = None,
    analysis_angles: Optional[List[str]] = None,
    locale: str | None = None,
) -> DashboardPresentation:
    """调用 LLM 生成看板分类与生动文案；失败时回退规则兜底。"""
    if not panels:
        return DashboardPresentation(
            headline=f"{plan.scope_label or plan.matched_event} 分析",
            summary=plan.statistical_caliber.description,
            sections=[],
            panels=[],
        )

    panel_ids = {p.panel_id for p in panels}

    try:
        client = _create_client()
    except MissingApiKeyError:
        return _fallback_presentation(panels, plan)

    system_prompt = _build_narrator_prompt(
        panels,
        plan,
        query,
        scope_event_count=scope_event_count,
        depth_insights=depth_insights,
        analysis_angles=analysis_angles,
    ) + locale_instruction(locale)

    try:
        response = client.chat.completions.create(
            model=get_deepseek_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请生成看板分类与生动文案。"},
            ],
            response_format={"type": "json_object"},
            temperature=0.55,
        )
    except Exception as exc:
        if isinstance(exc, LLMApiError):
            raise
        return _fallback_presentation(panels, plan)

    if not response.choices:
        return _fallback_presentation(panels, plan)

    raw_output = response.choices[0].message.content or ""
    try:
        data = _parse_llm_json(raw_output)
        return _validate_presentation(data, raw_output, panel_ids)
    except AnalysisPlanError:
        return _fallback_presentation(panels, plan)
