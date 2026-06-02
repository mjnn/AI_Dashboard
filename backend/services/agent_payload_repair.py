"""修复 LLM Agent 各阶段 JSON 与 Pydantic Schema 的常见偏差。"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from schemas.agent_plan import AgentContextBundle, VisualizationProposal
from services.llm_planner import (
    _coerce_formula_components,
    _extract_formula_ids_from_expression,
)
from services.analysis_intent import normalize_agent_intent_fields
from services.analysis_registry import get_analysis_spec, wants_comprehensive_analysis


def _default_metrics(analysis_type: str) -> List[dict[str, Any]]:
    if analysis_type == "funnel":
        return [
            {"id": "user_count", "name": "到达车辆数", "type": "count"},
            {"id": "conversion_rate", "name": "步间转化率(%)", "type": "count"},
        ]
    if analysis_type in ("summary_kpi", "time_series", "event_comparison", "growth_rate"):
        return [
            {"id": "pv", "name": "触发次数", "type": "count"},
            {"id": "uv", "name": "按车去重", "type": "nunique", "field": "vin_code"},
        ]
    return [{"id": "pv", "name": "触发次数", "type": "count"}]


def repair_time_range(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        tr = dict(value)
        if tr.get("type") == "last_n_days":
            tr.setdefault("value", 30)
            return tr
        if tr.get("type") == "date_range":
            return tr
    if isinstance(value, str):
        text = value.lower().replace("_", " ")
        match = re.search(r"(\d+)", text)
        days = int(match.group(1)) if match else 30
        return {"type": "last_n_days", "value": days}
    if isinstance(value, int):
        return {"type": "last_n_days", "value": value}
    return {"type": "last_n_days", "value": 30}


def repair_comparison_events(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, dict):
        # LLM 有时输出 csv->字典 映射对象
        if all(isinstance(v, str) for v in value.values()):
            return [str(v) for v in value.values()]
        return [str(k) for k in value.keys()]
    return [str(value)]


def repair_csv_event_filter(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, dict):
        return [str(k) for k in value.keys()]
    return [str(value)]


_EVENT_FILTER_KEYS = frozenset(
    {"csv_event_filter", "event_filter", "events", "event", "event_name"}
)


def repair_filters(
    filters: Any,
    *,
    csv_event_filter: List[str],
) -> tuple[List[str], dict[str, str]]:
    """filters 只允许 string 值；误放的 event 列表提升到 csv_event_filter。"""
    merged_events = list(csv_event_filter)
    repaired: dict[str, str] = {}
    if not isinstance(filters, dict):
        return merged_events, repaired

    for key, value in filters.items():
        key_norm = str(key).strip()
        if key_norm.lower() in _EVENT_FILTER_KEYS:
            merged_events.extend(repair_csv_event_filter(value))
            continue
        if isinstance(value, list):
            parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
            if parts:
                repaired[key_norm] = ",".join(parts)
            continue
        if isinstance(value, dict):
            inner = value.get("value") or value.get("values")
            if isinstance(inner, list):
                parts = [str(v).strip() for v in inner if v is not None and str(v).strip()]
                if parts:
                    repaired[key_norm] = ",".join(parts)
            elif inner is not None and str(inner).strip():
                repaired[key_norm] = str(inner).strip()
            continue
        if value is not None and str(value).strip():
            repaired[key_norm] = str(value).strip()

    deduped: List[str] = []
    seen: set[str] = set()
    for item in merged_events:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped, repaired


_METRIC_TYPE_ALIASES = {
    "rate": "count",
    "ratio": "count",
    "percent": "count",
    "percentage": "count",
    "avg": "count",
    "average": "count",
    "unique": "nunique",
    "distinct": "nunique",
    "n_unique": "nunique",
}


def _coerce_metric_type(raw: Any) -> str:
    value = str(raw or "count").lower().strip()
    if value in ("count", "nunique", "formula"):
        return value
    return _METRIC_TYPE_ALIASES.get(value, "count")


def repair_metrics(value: Any, analysis_type: str) -> List[dict[str, Any]]:
    if not value:
        return _default_metrics(analysis_type)
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return _default_metrics(analysis_type)
    repaired: List[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        metric = dict(item)
        metric.setdefault("id", "pv")
        metric.setdefault("name", metric["id"])
        metric["type"] = _coerce_metric_type(metric.get("type"))
        if metric["type"] == "nunique" and not metric.get("field"):
            metric["field"] = "vin_code"
        if metric.get("type") == "nunique" and metric.get("field") == "vin_code":
            if str(metric.get("name", "")).strip() in {
                "独立车辆",
                "独立车辆数",
                "独立用户数",
                "UV",
                "uv",
            }:
                metric["name"] = "按车去重"
        if metric.get("type") == "formula" or "formula_components" in metric:
            coerced = _coerce_formula_components(metric.get("formula_components"))
            if not coerced and metric.get("formula"):
                coerced = _extract_formula_ids_from_expression(str(metric["formula"]))
            if coerced:
                metric["formula_components"] = coerced
            else:
                metric.pop("formula_components", None)
                if metric.get("type") == "formula" and not metric.get("formula"):
                    metric["type"] = "count"
        repaired.append(metric)
    return repaired or _default_metrics(analysis_type)


def repair_visualization_item(
    item: dict[str, Any],
    context: AgentContextBundle,
    *,
    fallback: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    base = dict(fallback or {})
    merged = {**base, **{k: v for k, v in item.items() if k != "data_requirements"}}

    dr_raw = item.get("data_requirements")
    if not isinstance(dr_raw, dict):
        dr_raw = {}
    base_dr = dict((fallback or {}).get("data_requirements") or {})
    dr = {**base_dr, **dr_raw}

    for key in (
        "csv_event_filter",
        "comparison_events",
        "dimension",
        "sub_dimension",
        "metrics",
        "filters",
        "time_range",
        "top_n",
        "cohort_retention_days",
        "period_unit",
    ):
        if key in item and key not in dr_raw:
            dr[key] = item[key]

    analysis_type = str(
        merged.get("analysis_type")
        or dr.get("analysis_type")
        or base.get("analysis_type")
        or "time_series"
    )
    spec = get_analysis_spec(analysis_type)
    default_chart = spec["default_chart"] if spec else "bar"
    default_dimension = spec["dimension"] if spec else "date"

    merged["panel_id"] = str(merged.get("panel_id") or "primary")
    merged["analysis_type"] = analysis_type
    merged.setdefault("chart_type", default_chart)
    merged.setdefault("layout", "single")
    merged.setdefault(
        "title",
        context.story.headline or context.dictionary.matched_event,
    )
    merged.setdefault(
        "reasoning",
        merged.get("reasoning") or context.story.narrative[:120] or "可视化规划",
    )

    dr["dimension"] = str(dr.get("dimension") or default_dimension)
    csv_filter = repair_csv_event_filter(dr.get("csv_event_filter"))
    csv_filter, dr["filters"] = repair_filters(dr.get("filters"), csv_event_filter=csv_filter)
    if not csv_filter:
        csv_filter = repair_csv_event_filter(context.dictionary.csv_event_filter)
    dr["csv_event_filter"] = csv_filter
    dr["comparison_events"] = repair_comparison_events(
        dr.get("comparison_events") or context.dictionary.comparison_events
    )
    dr["metrics"] = repair_metrics(dr.get("metrics"), analysis_type)
    dr["time_range"] = repair_time_range(dr.get("time_range"))

    merged["data_requirements"] = dr
    return merged


def repair_visualizations_payload(
    data: dict[str, Any],
    context: AgentContextBundle,
    *,
    previous: Optional[List[VisualizationProposal]] = None,
) -> dict[str, Any]:
    """规范化 visualizations 列表，供 AgentVisualization/RevisionPayload 校验。"""
    result = dict(data)
    raw = (
        result.get("visualizations")
        or result.get("visualization")
        or result.get("panels")
        or []
    )
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raw = []

    prev_map: dict[str, dict[str, Any]] = {}
    if previous:
        for proposal in previous:
            prev_map[proposal.panel_id] = proposal.model_dump()

    repaired: List[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        panel_id = str(item.get("panel_id") or f"panel-{index}")
        item = {**item, "panel_id": panel_id}
        repaired.append(
            repair_visualization_item(
                item,
                context,
                fallback=prev_map.get(panel_id),
            )
        )

    if not repaired and previous:
        repaired = [
            repair_visualization_item(p.model_dump(), context, fallback=p.model_dump())
            for p in previous
        ]

    if not repaired:
        repaired = [
            repair_visualization_item(
                {
                    "panel_id": "primary",
                    "analysis_type": "summary_kpi",
                },
                context,
            )
        ]

    result["visualizations"] = repaired
    if "revision_summary" in result or previous:
        result.setdefault("revision_summary", "")
    return result


def apply_query_intent_hints(
    context: AgentContextBundle,
    query: str,
) -> AgentContextBundle:
    normalized = normalize_agent_intent_fields(context.intent.model_dump(), query)
    context = context.model_copy(
        update={"intent": context.intent.model_copy(update=normalized)}
    )
    if context.intent.scope_mode == "comprehensive":
        context.intent.exploratory_mode = True
        if not context.intent.user_focus:
            context.intent.user_focus = "综合分析"
    elif context.intent.scope_mode == "single_event":
        context.intent.exploratory_mode = False
    return context


def repair_context_payload(data: dict[str, Any], *, query: str = "") -> dict[str, Any]:
    """阶段 1 轻量修复。"""
    result = dict(data)
    if "dictionary" in result and isinstance(result["dictionary"], dict):
        d = result["dictionary"]
        d["csv_event_filter"] = repair_csv_event_filter(d.get("csv_event_filter"))
        d["comparison_events"] = repair_comparison_events(d.get("comparison_events"))
        d.setdefault("related_events", [])
        d.setdefault("match_confidence", "medium")
    if "intent" in result and isinstance(result["intent"], dict):
        result["intent"] = normalize_agent_intent_fields(result["intent"], query)
    if "story" in result and isinstance(result["story"], dict):
        s = result["story"]
        s.setdefault("headline", s.get("narrative", "分析看板")[:40])
        s.setdefault("narrative", s.get("headline", "数据分析"))
    return result
