"""元数据解析服务。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from schemas.analysis import AnalysisPlan, MetricDef
from services.field_resolver import (
    MetadataResolverError,
    lookup_event,
    resolve_column_name,
    resolve_event,
)

_TIME_HINTS = ["date", "time", "timestamp", "datetime", "日期", "时间"]
_EVENT_HINTS = ["event", "事件", "eventname", "event_name", "事件名", "事件名称"]


def _lookup_event(
    events_index: dict,
    event_name: str,
    *,
    csv_event_names: Optional[List[str]] = None,
    query: str = "",
) -> dict:
    return lookup_event(
        events_index,
        event_name,
        csv_event_names=csv_event_names,
        query=query,
    )


def _attribute_names(event_def: dict) -> List[str]:
    attributes = event_def.get("attributes", {})
    names: List[str] = []
    for attr_name, meta in attributes.items():
        names.append(attr_name)
        cn_name = meta.get("cn_name")
        if cn_name:
            names.append(str(cn_name).split("\n")[0])
    return names


def _build_column_hints(
    plan: AnalysisPlan,
    event_def: dict,
    csv_columns: Optional[List[str]] = None,
) -> dict[str, list[str]]:
    attr_names = _attribute_names(event_def)

    event_col_hints = list(dict.fromkeys(_EVENT_HINTS + attr_names))
    time_col_hints = list(
        dict.fromkeys(_TIME_HINTS + [a for a in attr_names if _looks_like_time(a)])
    )

    dimension_col_hints = _hints_for_field(plan.dimension, attr_names)
    if plan.sub_dimension:
        dimension_col_hints.extend(
            _hints_for_field(plan.sub_dimension, attr_names)
        )
    dimension_col_hints = list(dict.fromkeys(dimension_col_hints))

    metric_field_hints: dict[str, list[str]] = {}
    for metric in plan.metrics:
        if metric.type == "nunique" and metric.field:
            metric_field_hints[metric.field] = _hints_for_field(
                metric.field, attr_names
            )

    for field_name in plan.filters:
        if field_name not in metric_field_hints:
            metric_field_hints[field_name] = _hints_for_field(field_name, attr_names)

    if csv_columns:
        for field in [plan.dimension, plan.sub_dimension, *(m.field for m in plan.metrics if m.field)]:
            if not field:
                continue
            resolved = resolve_column_name(field, csv_columns, event_def)
            if resolved and resolved not in dimension_col_hints:
                dimension_col_hints.append(resolved)

    return {
        "event_col_hints": event_col_hints,
        "time_col_hints": time_col_hints,
        "dimension_col_hints": dimension_col_hints,
        "metric_field_hints": metric_field_hints,
    }


def _looks_like_time(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in ("date", "time", "timestamp", "日期", "时间"))


def _hints_for_field(field: str, attr_names: List[str]) -> List[str]:
    hints = [field]
    field_lower = field.lower()

    for attr in attr_names:
        attr_lower = attr.lower()
        if field_lower in attr_lower or attr_lower in field_lower:
            hints.append(attr)

    common_aliases = {
        "date": ["date", "time", "timestamp", "datetime", "日期", "时间"],
        "vin_code": ["vin_code", "vin", "vehicle_vin", "VIN"],
        "vehicle_model": ["vehicle_model", "model", "车型"],
    }
    if field in common_aliases:
        hints.extend(common_aliases[field])

    return list(dict.fromkeys(hints))


def _build_aggregation_spec(plan: AnalysisPlan) -> dict:
    groupby_cols: List[str] = [plan.dimension]
    if plan.sub_dimension:
        groupby_cols.append(plan.sub_dimension)

    aggs: List[dict[str, Any]] = []
    for metric in plan.metrics:
        agg: dict[str, Any] = {"id": metric.id, "method": metric.type}
        if metric.type == "nunique" and metric.field:
            agg["field"] = metric.field
        if metric.type == "formula":
            agg["formula"] = metric.formula
            agg["components"] = metric.formula_components or []
        aggs.append(agg)

    return {
        "groupby_col": groupby_cols[0] if len(groupby_cols) == 1 else groupby_cols,
        "aggs": aggs,
    }


def resolve(
    plan: AnalysisPlan,
    events_index: dict,
    *,
    csv_event_names: Optional[List[str]] = None,
    csv_columns: Optional[List[str]] = None,
    query: str = "",
) -> dict:
    """根据分析计划与字典索引，输出列匹配提示与聚合指令。"""
    resolution = resolve_event(
        plan.matched_event,
        events_index,
        csv_event_names=csv_event_names,
        query=query or plan.matched_event,
    )
    event_def = resolution.event_def
    csv_column_hints = _build_column_hints(plan, event_def, csv_columns)
    aggregation_spec = _build_aggregation_spec(plan)

    return {
        "event_def": event_def,
        "csv_column_hints": csv_column_hints,
        "aggregation_spec": aggregation_spec,
        "event_resolution": {
            "match_method": resolution.match_method,
            "unmapped": resolution.unmapped,
            "csv_labels": list(resolution.csv_labels),
        },
    }
