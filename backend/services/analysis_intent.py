"""分析意图与事件范围 — Agent 结构化输出为主，正则仅作 legacy fallback。"""

from __future__ import annotations

from typing import Literal, Optional

from schemas.agent_plan import AgentContextBundle
from schemas.analysis import AnalysisPlan
from services.analysis_registry import (
    wants_comprehensive_analysis,
    wants_funnel_analysis,
    wants_usage_frequency_analysis,
)

ScopeMode = Literal["single_event", "event_list", "module", "comprehensive"]

SCOPE_MODES: tuple[ScopeMode, ...] = (
    "single_event",
    "event_list",
    "module",
    "comprehensive",
)


def normalize_scope_mode(value: object) -> Optional[ScopeMode]:
    if value in SCOPE_MODES:
        return value  # type: ignore[return-value]
    return None


def infer_scope_mode_fallback(
    query: str,
    *,
    analysis_mode: str = "auto",
) -> ScopeMode:
    """无 Agent 字段时的范围 fallback（尽量保守，默认单事件）。"""
    if wants_comprehensive_analysis(query) or analysis_mode == "exploratory":
        return "comprehensive"
    if wants_usage_frequency_analysis(query):
        return "single_event"
    return "single_event"


def infer_intent_type_fallback(query: str) -> Optional[str]:
    if wants_usage_frequency_analysis(query):
        return "usage_retention"
    if wants_funnel_analysis(query):
        return "funnel"
    if wants_comprehensive_analysis(query):
        return None
    return None


def normalize_agent_intent_fields(intent: dict, query: str) -> dict:
    """补全 Agent intent 字段；不覆盖 LLM 已显式给出的 scope_mode / intent_type。"""
    out = dict(intent)
    if wants_funnel_analysis(query):
        out["intent_type"] = "funnel"
        out["exploratory_mode"] = False
        mode = normalize_scope_mode(out.get("scope_mode"))
        if mode in (None, "comprehensive", "module"):
            out["scope_mode"] = "event_list"
    elif normalize_scope_mode(out.get("scope_mode")) is None:
        out["scope_mode"] = infer_scope_mode_fallback(query)
    else:
        out["scope_mode"] = normalize_scope_mode(out.get("scope_mode"))
    if not out.get("intent_type"):
        fallback = infer_intent_type_fallback(query)
        if fallback:
            out["intent_type"] = fallback
    out.setdefault("intent_confidence", "medium")
    out.setdefault("exploratory_mode", out.get("scope_mode") == "comprehensive")
    return out


def effective_scope_mode(
    *,
    query: str,
    plan: AnalysisPlan,
    agent_context: Optional[AgentContextBundle] = None,
    analysis_mode: str = "auto",
) -> ScopeMode:
    if agent_context is not None:
        mode = normalize_scope_mode(agent_context.intent.scope_mode)
        if mode is not None:
            return mode
    if plan.scope_mode:
        mode = normalize_scope_mode(plan.scope_mode)
        if mode is not None:
            return mode
    return infer_scope_mode_fallback(query, analysis_mode=analysis_mode)


def should_widen_event_scope(
    scope_mode: ScopeMode,
    query: str,
    analysis_mode: str = "auto",
) -> bool:
    """是否允许扩大 csv_event_filter（非 single_event 或用户明确要求全面分析）。"""
    if wants_comprehensive_analysis(query) or analysis_mode == "exploratory":
        return True
    return scope_mode != "single_event"


def should_run_multi_event_dashboard(
    scope_mode: ScopeMode,
    query: str,
    analysis_mode: str = "auto",
) -> bool:
    """是否进入多事件综合看板（非单图）。"""
    if wants_comprehensive_analysis(query) or analysis_mode == "exploratory":
        return True
    return scope_mode == "comprehensive"
