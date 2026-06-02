"""Agent 式分析规划：意图 → 字典 → 故事 → 可视化 ↔ 数据校验循环 → 出图计划。"""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional, Tuple

import pandas as pd
from pydantic import ValidationError

from schemas.agent_plan import (
    AgentContextBundle,
    AgentContextPayload,
    AgentExecutionTrace,
    AgentRevisionPayload,
    AgentRoundTrace,
    AgentStory,
    AgentVisualizationPayload,
    DataFeasibilityCheck,
    VisualizationProposal,
)
from schemas.analysis import AnalysisPlan
from services.analysis_registry import (
    build_analysis_catalog_prompt,
    build_chart_catalog_prompt,
    normalize_plan_for_analysis,
    repair_funnel_analysis_plan,
    wants_comprehensive_analysis,
    wants_funnel_analysis,
    wants_usage_frequency_analysis,
)
from services.agent_payload_repair import (
    apply_query_intent_hints,
    repair_context_payload,
    repair_visualizations_payload,
)
from services.analysis_route_memory import (
    build_route_signature,
    lookup_route,
    remember_route,
    route_cache_enabled,
    should_bypass_cache,
    skip_feasibility_on_cache_hit,
    story_always_fresh,
)
from services.data_feasibility import check_all_proposals, _requirements_to_plan
from services.event_mapping import repair_plan_event_adaptation
from services.llm_planner import (
    AnalysisPlanError,
    LLMApiError,
    MissingApiKeyError,
    _parse_llm_json,
    _validate_plan,
    build_events_whitelist,
    repair_plan_llm_payload,
)
from services.llm_settings import get_deepseek_model
from services.locale import locale_instruction

logger = logging.getLogger(__name__)

AGENT_REQUEST_TIMEOUT = float(os.getenv("ANALYSIS_AGENT_TIMEOUT", "25"))
MAX_AGENT_ROUNDS = int(os.getenv("ANALYSIS_AGENT_MAX_ROUNDS", "3"))


def _should_refresh_story_on_cache_hit(
    context: AgentContextBundle,
    query: str,
) -> bool:
    if not story_always_fresh():
        return False
    if wants_comprehensive_analysis(query):
        return False
    if context.intent.scope_mode == "single_event":
        return False
    if wants_usage_frequency_analysis(query):
        return False
    return True


def _synthetic_ready_feedback(
    proposals: List[VisualizationProposal],
) -> List[DataFeasibilityCheck]:
    return [
        DataFeasibilityCheck(
            panel_id=p.panel_id,
            ready=True,
            filtered_rows=0,
            preview_rows=1,
        )
        for p in proposals
    ]


def _chat_json(system: str, user: str, *, temperature: float = 0.15) -> dict:
    from openai import OpenAI

    from config import get_deepseek_api_key
    from services.llm_planner import DEEPSEEK_BASE_URL

    api_key = get_deepseek_api_key()
    if not api_key:
        raise MissingApiKeyError(
            "DEEPSEEK_API_KEY 未配置，请在 backend/.env 中设置 DEEPSEEK_API_KEY"
        )
    client = OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        timeout=AGENT_REQUEST_TIMEOUT,
    )
    response = client.chat.completions.create(
        model=get_deepseek_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    if not response.choices:
        raise LLMApiError("DeepSeek API 返回为空")
    raw = response.choices[0].message.content or ""
    return _parse_llm_json(raw)


def _build_phase1_system(
    events_whitelist: str,
    csv_hint: str,
    *,
    locale: str | None,
) -> str:
    return f"""你是座舱埋点分析 Agent 的第一阶段：理解意图、查询字典、讲述分析故事。
不要规划图表，不要输出 analysis_type / chart_type。

{events_whitelist}

{csv_hint}

{locale_instruction(locale)}

## 执行顺序（必须按此思考）
1. **识别意图**：用户想回答什么业务问题？填写 intent_type（注册表 analysis_type）与 scope_mode。
2. **scope_mode 规则**：
   - single_event：只分析一个字典事件（如某事件的频次、趋势）
   - event_list：用户明确给出多个事件对比/列表
   - module：用户明确要整个功能模块（如「分析 carlog 模块」）但未要求「综合/全面」
   - comprehensive：用户要求综合/全面/整体分析
3. **查询字典**：matched_event、matched_module、csv_event_filter（必填，来自 CSV event 列真实取值）。
4. **讲述故事**：headline + narrative、takeaway。

## 输出 JSON
{{
  "intent": {{
    "goal": "...",
    "intent_confidence": "high|medium|low",
    "intent_type": "usage_retention|funnel|time_series|...",
    "scope_mode": "single_event|event_list|module|comprehensive",
    "exploratory_mode": false,
    "user_focus": "漏斗|趋势|对比|留存|..."
  }},
  "dictionary": {{
    "matched_event": "字典事件名",
    "matched_module": "模块名",
    "match_confidence": "high|medium|low",
    "related_events": ["..."],
    "csv_event_filter": ["数据池event取值"],
    "comparison_events": ["漏斗/对比时的有序字典事件名，可选"],
    "mapping_note": "字典名与CSV映射说明"
  }},
  "story": {{
    "headline": "看板标题",
    "narrative": "2-4句分析故事",
    "takeaway": "一句结论导向"
  }}
}}
只输出 JSON。"""


def _build_phase2_system(
    events_whitelist: str,
    csv_hint: str,
    catalog: str,
    chart_catalog: str,
    *,
    locale: str | None,
) -> str:
    return f"""你是座舱埋点分析 Agent 的第二阶段：规划可视化对象（图表类型）并声明所需数据。
此时意图、字典、故事已由前一阶段完成；你必须输出可被执行层校验的 data_requirements。

{events_whitelist}
{csv_hint}
{catalog}
{chart_catalog}

{locale_instruction(locale)}

## 执行顺序
1. 基于故事选择 1 个主可视化（panel_id=primary）；复杂问题可最多 3 个，但通常 1 个即可。
2. 为每个可视化指定 analysis_type、chart_type（必须属于该类型的可选图表）、title、reasoning。
3. 填写 data_requirements：csv_event_filter、metrics、dimension、time_range、comparison_events（漏斗必填）等。
4. 不要编造 CSV 中不存在的列或 event 取值。

## 输出 JSON
{{
  "story_refined": "可选，对故事的微调",
  "visualizations": [
    {{
      "panel_id": "primary",
      "analysis_type": "funnel",
      "chart_type": "funnel_chart",
      "layout": "single",
      "title": "...",
      "reasoning": "...",
      "data_requirements": {{
        "csv_event_filter": ["carlog_entry", "..."],
        "comparison_events": ["Carlog_进入", "..."],
        "dimension": "漏斗步骤",
        "metrics": [{{"id":"user_count","name":"到达车辆数","type":"count"}}],
        "filters": {{}},
        "time_range": {{"type":"last_n_days","value":30}}
      }}
    }}
  ]
}}
只输出 JSON。"""


def _build_revision_system(
    catalog: str,
    chart_catalog: str,
    *,
    locale: str | None,
) -> str:
    return f"""你是座舱埋点分析 Agent 的修订阶段：根据**代码数据校验反馈**调整可视化方案。

{catalog}
{chart_catalog}

{locale_instruction(locale)}

## 规则
- 必须逐条解决 feedback 中的 issues；可参考 suggestions。
- 可更换 analysis_type / chart_type / csv_event_filter / 时间范围 / 指标。
- 修订后 data_requirements 必须能被同一套校验器通过。
- revision_summary 用 1-2 句话说明改了什么。

## 输出 JSON
{{
  "revision_summary": "...",
  "visualizations": [ ... 同第二阶段结构 ... ]
}}
只输出 JSON。"""


def _format_feedback_for_llm(
    feedback: List[DataFeasibilityCheck],
) -> str:
    blocks = []
    for item in feedback:
        blocks.append(
            {
                "panel_id": item.panel_id,
                "ready": item.ready,
                "filtered_rows": item.filtered_rows,
                "preview_rows": item.preview_rows,
                "issues": item.issues,
                "warnings": item.warnings,
                "suggestions": item.suggestions,
            }
        )
    return json.dumps(blocks, ensure_ascii=False, indent=2)


def _llm_phase_context(
    query: str,
    events_whitelist: str,
    csv_hint: str,
    *,
    locale: str | None,
) -> AgentContextBundle:
    system = _build_phase1_system(events_whitelist, csv_hint, locale=locale)
    data = _chat_json(system, query)
    data = repair_context_payload(data, query=query)
    try:
        payload = AgentContextPayload.model_validate(data)
    except ValidationError as exc:
        raise AnalysisPlanError(f"Agent 意图阶段校验失败: {exc}") from exc
    return AgentContextBundle(
        intent=payload.intent,
        dictionary=payload.dictionary,
        story=payload.story,
    )


def _llm_phase_visualization(
    query: str,
    context: AgentContextBundle,
    events_whitelist: str,
    csv_hint: str,
    *,
    locale: str | None,
    feedback: List[DataFeasibilityCheck] | None = None,
    previous: Optional[List[VisualizationProposal]] = None,
) -> List[VisualizationProposal]:
    catalog = build_analysis_catalog_prompt()
    chart_catalog = build_chart_catalog_prompt()
    if feedback:
        system = _build_revision_system(catalog, chart_catalog, locale=locale)
        user = (
            f"## 用户问题\n{query}\n\n"
            f"## 已确定上下文\n{context.model_dump_json(ensure_ascii=False)}\n\n"
            f"## 代码校验反馈（必须解决所有 issues）\n{_format_feedback_for_llm(feedback)}\n\n"
            "请输出修订后的 visualizations。"
        )
        data = _chat_json(system, user)
        data = repair_visualizations_payload(
            data, context, previous=previous
        )
        try:
            payload = AgentRevisionPayload.model_validate(data)
        except ValidationError as exc:
            raise AnalysisPlanError(f"Agent 修订阶段校验失败: {exc}") from exc
        return payload.visualizations

    system = _build_phase2_system(
        events_whitelist,
        csv_hint,
        catalog,
        chart_catalog,
        locale=locale,
    )
    user = (
        f"## 用户问题\n{query}\n\n"
        f"## 已确定上下文\n{context.model_dump_json(ensure_ascii=False)}\n\n"
        "请规划可视化对象并填写 data_requirements。"
    )
    data = _chat_json(system, user)
    data = repair_visualizations_payload(data, context)
    try:
        payload = AgentVisualizationPayload.model_validate(data)
    except ValidationError as exc:
        raise AnalysisPlanError(f"Agent 可视化阶段校验失败: {exc}") from exc
    if payload.story_refined:
        context.story.narrative = (
            f"{context.story.narrative} {payload.story_refined}".strip()
        )
    return payload.visualizations


def _llm_refresh_story(
    query: str,
    context: AgentContextBundle,
    csv_hint: str,
    *,
    locale: str | None,
) -> AgentStory:
    """缓存命中后仍刷新故事层，保留 LLM 叙事与想象力空间。"""
    system = f"""你是座舱埋点分析的 storyteller。
分析路线（事件范围、指标、图表类型）已由系统确定，请勿修改字典或数据范围。
请根据用户问题与当前数据上下文，撰写**新鲜**的看板故事：标题、叙述、结论导向。

{csv_hint}

{locale_instruction(locale)}

## 输出 JSON
{{
  "headline": "看板标题",
  "narrative": "2-4句分析故事，可提出新的业务洞察角度",
  "takeaway": "一句结论导向"
}}
只输出 JSON。"""
    user = (
        f"## 用户问题\n{query}\n\n"
        f"## 已确定路线（勿改事件/指标结构）\n"
        f"{context.model_dump_json(ensure_ascii=False)}"
    )
    data = _chat_json(system, user, temperature=0.55)
    try:
        story = AgentStory.model_validate(data)
    except ValidationError:
        return context.story
    return story


def _pick_best_proposal(
    proposals: List[VisualizationProposal],
    feedback: List[DataFeasibilityCheck],
    *,
    prefer_non_funnel: bool = False,
    prefer_usage_retention: bool = False,
    prefer_funnel: bool = False,
) -> Tuple[VisualizationProposal, DataFeasibilityCheck]:
    fb_map = {f.panel_id: f for f in feedback}
    candidates = proposals
    if prefer_usage_retention:
        usage = [
            p
            for p in proposals
            if p.analysis_type in ("usage_retention", "usage_distribution")
        ]
        if usage:
            candidates = usage
    elif prefer_funnel:
        funnel = [p for p in proposals if p.analysis_type == "funnel"]
        if funnel:
            candidates = funnel
    elif prefer_non_funnel:
        non_funnel = [p for p in proposals if p.analysis_type != "funnel"]
        if non_funnel:
            candidates = non_funnel
    for proposal in candidates:
        fb = fb_map.get(proposal.panel_id)
        if fb and fb.ready:
            return proposal, fb
    for proposal in candidates:
        fb = fb_map.get(proposal.panel_id)
        if fb and fb.preview_rows > 0:
            return proposal, fb
    return candidates[0], fb_map[candidates[0].panel_id]


def _proposal_to_validated_plan(
    proposal: VisualizationProposal,
    context: AgentContextBundle,
    *,
    events_index: dict,
    csv_event_names: List[str],
    query: str,
) -> AnalysisPlan:
    plan = _requirements_to_plan(proposal, context)
    raw = plan.model_dump()
    if events_index and csv_event_names:
        raw = repair_plan_event_adaptation(raw, events_index, csv_event_names, query)
    raw = repair_plan_llm_payload(
        raw,
        query=query,
        csv_event_names=csv_event_names,
        events_index=events_index,
    )
    plan = _validate_plan(
        raw,
        "",
        events_index,
        csv_event_names=csv_event_names,
        query=query,
    )
    plan = normalize_plan_for_analysis(plan, query=query)
    updates: dict = {}
    if context.intent.scope_mode:
        updates["scope_mode"] = context.intent.scope_mode
    if context.intent.intent_type and not plan.analysis_type:
        updates["analysis_type"] = context.intent.intent_type
    if updates:
        plan = plan.model_copy(update=updates)
    return plan


def generate_plan_via_agent(
    query: str,
    events_whitelist: str,
    *,
    events_index: dict,
    csv_event_names: List[str],
    csv_columns: List[str],
    df: pd.DataFrame,
    locale: str | None = None,
    force_fresh: bool = False,
) -> Tuple[AnalysisPlan, AgentExecutionTrace]:
    """
  Agent 规划主入口：
  意图 → 字典 → 故事 → [可视化规划 ↔ 代码校验]×N → AnalysisPlan
    """
    from services.llm_planner import _build_csv_events_hint

    csv_hint = _build_csv_events_hint(csv_event_names, csv_columns, events_index)
    trace_rounds: List[AgentRoundTrace] = []
    cache_hit = False
    phases_skipped: List[str] = []
    signature = build_route_signature(query)

    context: AgentContextBundle
    proposals: List[VisualizationProposal] = []
    feedback: Optional[List[DataFeasibilityCheck]] = None
    converged = False

    cached = None
    if route_cache_enabled() and not should_bypass_cache(query, force_fresh=force_fresh):
        cached = lookup_route(query, locale=locale)

    if cached is not None:
        context = cached.context.model_copy(deep=True)
        context = apply_query_intent_hints(context, query)
        proposals = [item.model_copy(deep=True) for item in cached.proposals]
        if cached.converged and skip_feasibility_on_cache_hit():
            feedback = _synthetic_ready_feedback(proposals)
            cache_hit = True
            converged = True
            phases_skipped = [
                "intent_dictionary",
                "visualization_loop",
                "feasibility_dry_run",
            ]
            logger.info(
                "分析路线缓存复用 signature=%s（跳过可行性 dry-run）",
                signature,
            )
            if _should_refresh_story_on_cache_hit(context, query):
                try:
                    context.story = _llm_refresh_story(
                        query, context, csv_hint, locale=locale
                    )
                except (LLMApiError, AnalysisPlanError) as exc:
                    logger.warning("故事刷新失败，保留缓存故事: %s", exc)
        else:
            feedback = check_all_proposals(
                proposals,
                context,
                df=df,
                columns=csv_columns,
                csv_event_names=csv_event_names,
                events_index=events_index,
                query=query,
            )
            if all(item.ready for item in feedback):
                cache_hit = True
                converged = True
                phases_skipped = ["intent_dictionary", "visualization_loop"]
                logger.info("分析路线缓存复用 signature=%s", signature)
                if _should_refresh_story_on_cache_hit(context, query):
                    try:
                        context.story = _llm_refresh_story(
                            query, context, csv_hint, locale=locale
                        )
                    except (LLMApiError, AnalysisPlanError) as exc:
                        logger.warning("故事刷新失败，保留缓存故事: %s", exc)
            else:
                logger.info("缓存方案未通过当前数据校验，回退完整 Agent")
                cached = None

    if not cache_hit:
        logger.info("Agent phase 1: intent + dictionary + story")
        context = _llm_phase_context(
            query, events_whitelist, csv_hint, locale=locale
        )
        context = apply_query_intent_hints(context, query)

        feedback = None
        proposals = []
        converged = False

        for round_idx in range(1, MAX_AGENT_ROUNDS + 1):
            logger.info("Agent round %d: visualization planning", round_idx)
            proposals = _llm_phase_visualization(
                query,
                context,
                events_whitelist,
                csv_hint,
                locale=locale,
                feedback=feedback,
                previous=proposals if feedback else None,
            )
            feedback = check_all_proposals(
                proposals,
                context,
                df=df,
                columns=csv_columns,
                csv_event_names=csv_event_names,
                events_index=events_index,
                query=query,
            )
            trace_rounds.append(
                AgentRoundTrace(round=round_idx, proposals=proposals, feedback=feedback)
            )
            if all(item.ready for item in feedback):
                converged = True
                logger.info("Agent converged at round %d", round_idx)
                break
            logger.warning(
                "Agent round %d not ready: %s",
                round_idx,
                [i.issues for i in feedback],
            )

        if converged and route_cache_enabled():
            remember_route(
                query,
                locale=locale,
                context=context,
                proposals=proposals,
                converged=True,
            )

    proposal, _best_fb = _pick_best_proposal(
        proposals,
        feedback or [],
        prefer_non_funnel=wants_comprehensive_analysis(query),
        prefer_usage_retention=wants_usage_frequency_analysis(query),
        prefer_funnel=wants_funnel_analysis(query),
    )
    plan = _proposal_to_validated_plan(
        proposal,
        context,
        events_index=events_index,
        csv_event_names=csv_event_names,
        query=query,
    )
    if wants_comprehensive_analysis(query):
        plan = plan.model_copy(update={"exploratory_mode": True})

    scope_on_plan = context.intent.scope_mode
    if scope_on_plan:
        plan = plan.model_copy(update={"scope_mode": scope_on_plan})

    trace = AgentExecutionTrace(
        context=context,
        rounds=trace_rounds,
        final_panel_id=proposal.panel_id,
        converged=converged,
        total_rounds=len(trace_rounds),
        cache_hit=cache_hit,
        cache_signature=signature if cache_hit else None,
        phases_skipped=phases_skipped,
    )
    return plan, trace
