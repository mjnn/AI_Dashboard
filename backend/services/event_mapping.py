"""字典 event 与 CSV event 列的双向适配 — LLM 为主、规则兜底。"""

from __future__ import annotations

from typing import List, Optional, Set

from services.field_resolver import _csv_labels_for_event, _lookup_in_index, resolve_event
from services.event_scope import infer_related_csv_events, _pick_primary_csv_label


def build_dict_csv_mapping_hint(
    events_index: dict,
    csv_event_names: List[str],
) -> str:
    """生成供 LLM 参考的字典↔CSV 映射表与未映射 CSV 事件。"""
    if not csv_event_names:
        return ""

    csv_set = {str(v) for v in csv_event_names}
    mapped_csv: Set[str] = set()
    lines: List[str] = [
        "## 字典事件 ↔ 数据池 event 列（格式可能不一致，分析过滤以 CSV 列值为准）",
        "输出时请同时填写 matched_event（字典名）与 csv_event_filter（实际 CSV event 取值列表）。",
    ]

    for canonical in sorted(events_index.get("events", {})):
        labels = _csv_labels_for_event(events_index, canonical, csv_event_names)
        if not labels:
            continue
        mapped_csv.update(labels)
        lines.append(f"- {canonical} → {', '.join(labels)}")

    unmapped = sorted(csv_set - mapped_csv)
    if unmapped:
        lines.append("## 数据池中尚未在字典建立映射的 event 取值（可直接写入 csv_event_filter）")
        for name in unmapped[:30]:
            lines.append(f"- {name}")

    return "\n".join(lines) + "\n"


def sanitize_csv_event_filter(
    values: List[str] | None,
    csv_event_names: List[str],
) -> List[str]:
    """只保留数据池中真实存在的 event 取值。"""
    if not values or not csv_event_names:
        return []
    pool = {str(v) for v in csv_event_names}
    return list(dict.fromkeys(v for v in values if str(v) in pool))


def infer_csv_filter_for_canonical(
    canonical: str,
    events_index: dict,
    csv_event_names: List[str],
) -> List[str]:
    """从字典 canonical 反查 CSV event 列取值。"""
    labels = _csv_labels_for_event(events_index, canonical, csv_event_names)
    if labels:
        return list(labels)
    if canonical in {str(v) for v in csv_event_names}:
        return [canonical]
    return []


def infer_csv_filter_for_comparison(
    comparison_events: List[str],
    events_index: dict,
    csv_event_names: List[str],
    query: str = "",
) -> List[str]:
    """漏斗/多事件对比：合并各字典事件的 CSV 取值。"""
    collected: List[str] = []
    for event_name in comparison_events:
        try:
            resolved = resolve_event(
                str(event_name),
                events_index,
                csv_event_names=csv_event_names,
                query=query,
            )
            collected.extend(resolved.csv_labels or infer_csv_filter_for_canonical(
                resolved.event_name, events_index, csv_event_names
            ))
        except Exception:
            if str(event_name) in {str(v) for v in csv_event_names}:
                collected.append(str(event_name))
    return list(dict.fromkeys(collected))


def resolve_event_filter(
    *,
    csv_event_filter: List[str] | None,
    matched_event: str,
    comparison_events: List[str] | None,
    events_index: dict,
    csv_event_names: List[str],
    query: str = "",
) -> tuple[set[str], str]:
    """
    确定最终 CSV 过滤集合与来源。
    优先级：LLM csv_event_filter > 字典反查 > 模块推断 > 单事件兜底。
    """
    sanitized = sanitize_csv_event_filter(csv_event_filter or [], csv_event_names)
    if sanitized:
        return set(sanitized), "llm_csv_filter"

    if comparison_events:
        inferred = infer_csv_filter_for_comparison(
            comparison_events, events_index, csv_event_names, query
        )
        if inferred:
            return set(inferred), "dict_comparison"

    labels = infer_csv_filter_for_canonical(matched_event, events_index, csv_event_names)
    if labels:
        return set(labels), "dict_canonical"

    related = infer_related_csv_events(query or matched_event, csv_event_names)
    if related:
        return related, "module_scope"

    try:
        resolved = resolve_event(
            matched_event,
            events_index,
            csv_event_names=csv_event_names,
            query=query,
        )
        if resolved.csv_labels:
            return set(resolved.csv_labels), "resolver"
    except Exception:
        pass

    pool = {str(v) for v in csv_event_names}
    if matched_event in pool:
        return {matched_event}, "literal"

    return set(), "empty"


def repair_plan_event_adaptation(
    data: dict,
    events_index: dict,
    csv_event_names: List[str],
    query: str,
) -> dict:
    """
    LLM 计划入库前：保留 LLM 的 csv_event_filter，仅在缺失时用规则补全；
    matched_event 与 csv_event_filter 不一致时以 filter 主事件为准校正锚点。
    """
    from services.event_scope import apply_module_anchor_event, module_primary_canonical

    updated = dict(data)
    llm_filter = sanitize_csv_event_filter(
        updated.get("csv_event_filter"), csv_event_names
    )
    match_confidence = str(updated.get("match_confidence", "medium")).lower()
    llm_provided_filter = bool(updated.get("csv_event_filter")) and bool(llm_filter)

    matched = str(updated.get("matched_event", "")).strip()
    if matched:
        resolved = resolve_event(
            matched,
            events_index,
            csv_event_names=csv_event_names,
            query=query,
        )
        updated["matched_event"] = resolved.event_name
        if resolved.event_def.get("module") and not updated.get("matched_module"):
            updated["matched_module"] = resolved.event_def["module"]

    if llm_provided_filter and match_confidence in ("high", "medium"):
        updated["csv_event_filter"] = llm_filter
        primary_label = _pick_primary_csv_label(set(llm_filter))
        canonical = _lookup_in_index(events_index, primary_label)
        if canonical:
            updated["matched_event"] = canonical
            module = events_index.get("events", {}).get(canonical, {}).get("module")
            if module:
                updated["matched_module"] = module
    else:
        module_canonical = module_primary_canonical(query, csv_event_names, events_index)
        if module_canonical and match_confidence != "high":
            updated["matched_event"] = module_canonical
            module = events_index.get("events", {}).get(module_canonical, {}).get("module")
            if module:
                updated["matched_module"] = module
            related = infer_related_csv_events(query, csv_event_names)
            if related:
                updated["csv_event_filter"] = sorted(related)
        elif not llm_filter:
            inferred = infer_csv_filter_for_canonical(
                updated.get("matched_event", ""), events_index, csv_event_names
            )
            related = infer_related_csv_events(query, csv_event_names)
            if related and len(related) > len(inferred):
                updated["csv_event_filter"] = sorted(related)
            elif inferred:
                updated["csv_event_filter"] = inferred
            else:
                updated["csv_event_filter"] = llm_filter
        else:
            updated["csv_event_filter"] = llm_filter

        if not llm_provided_filter:
            updated = apply_module_anchor_event(updated, query, csv_event_names, events_index)
            if not updated.get("csv_event_filter"):
                related = infer_related_csv_events(query, csv_event_names)
                if related:
                    updated["csv_event_filter"] = sorted(related)

    if updated.get("comparison_events"):
        canonical_events: list[str] = []
        for event_name in updated["comparison_events"]:
            try:
                canonical_events.append(
                    resolve_event(
                        str(event_name),
                        events_index,
                        csv_event_names=csv_event_names,
                        query=query,
                    ).event_name
                )
            except Exception:
                canonical_events.append(str(event_name))
        updated["comparison_events"] = canonical_events
        if not updated.get("csv_event_filter"):
            comp_filter = infer_csv_filter_for_comparison(
                canonical_events, events_index, csv_event_names, query
            )
            if comp_filter:
                updated["csv_event_filter"] = comp_filter

    return updated
