"""字段与事件解析 — CSV 数据为事实来源，字典为增强；避免白名单硬拒绝。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import List, Optional, Set

_NORMALIZE = re.compile(r"[\s_\-]+")


class MetadataResolverError(Exception):
    """事件或字段元数据解析失败。"""


def normalize_token(value: str) -> str:
    return _NORMALIZE.sub("", str(value).lower())


@dataclass(frozen=True)
class EventResolution:
    """事件解析结果。"""

    event_name: str
    event_def: dict
    match_method: str
    csv_labels: tuple[str, ...] = ()
    unmapped: bool = False


def virtual_event_def(csv_label: str) -> dict:
    """字典中无映射时，用 CSV event 值构造最小 event_def，保证过滤与聚合可继续。"""
    label = str(csv_label)
    return {
        "event_name": label,
        "module": "",
        "data_id": "",
        "condition": "",
        "attributes": {},
        "aliases": [label],
        "unmapped": True,
    }


def _event_def_from_index(events_index: dict, canonical: str) -> dict:
    events: dict = events_index.get("events", {})
    if canonical not in events:
        raise MetadataResolverError(f"事件 '{canonical}' 不在字典索引中")
    return {"event_name": canonical, **events[canonical]}


def _csv_labels_for_event(events_index: dict, canonical: str, csv_event_names: List[str]) -> tuple[str, ...]:
    if not csv_event_names:
        return ()
    csv_set = {str(v) for v in csv_event_names}
    definition = events_index.get("events", {}).get(canonical, {})
    matched = [alias for alias in definition.get("aliases", []) if str(alias) in csv_set]
    if canonical in csv_set:
        matched.append(canonical)
    return tuple(dict.fromkeys(matched))


def _score_event_for_context(
    canonical: str,
    events_index: dict,
    csv_event_names: List[str],
    query: str,
    hint: str,
) -> int:
    labels = _csv_labels_for_event(events_index, canonical, csv_event_names)
    if not labels:
        return 0
    score = len(labels)
    combined = f"{query} {hint}".lower()
    for label in labels:
        lower = label.lower()
        if lower in combined or lower.split("_", 1)[0] in combined:
            score += 20
        if normalize_token(label) == normalize_token(hint):
            score += 30
    if normalize_token(canonical) == normalize_token(hint):
        score += 10
    return score


def _pick_best_canonical(
    candidates: List[str],
    events_index: dict,
    csv_event_names: Optional[List[str]],
    query: str,
    hint: str,
) -> Optional[str]:
    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return unique[0]
    if not csv_event_names:
        return unique[0]

    scored = [
        (
            _score_event_for_context(name, events_index, csv_event_names, query, hint),
            name,
        )
        for name in unique
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored[0][0] > 0:
        return scored[0][1]
    if scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


def _lookup_in_index(events_index: dict, name: str) -> Optional[str]:
    events: dict = events_index.get("events", {})
    if name in events:
        return name

    alias_index: dict = events_index.get("alias_index", {})
    if name in alias_index:
        return alias_index[name]

    lower = name.lower()
    if lower in alias_index:
        return alias_index[lower]

    normalized_index: dict = events_index.get("normalized_index", {})
    normalized = normalize_token(name)
    if normalized in normalized_index:
        return normalized_index[normalized]

    for canonical, definition in events.items():
        if name in definition.get("aliases", []):
            return canonical

    for canonical, definition in events.items():
        if normalized == normalize_token(canonical):
            return canonical
        for alias in definition.get("aliases", []):
            if normalized == normalize_token(str(alias)):
                return canonical

    return None


def _resolve_from_csv_pool(
    hint: str,
    query: str,
    csv_event_names: List[str],
    events_index: dict,
) -> Optional[EventResolution]:
    if not csv_event_names:
        return None

    combined = f"{query} {hint}".lower()
    hint_norm = normalize_token(hint)
    matched_labels: List[str] = []

    from services.event_scope import extract_latin_tokens, infer_related_csv_events, _pick_primary_csv_label

    related = infer_related_csv_events(query or hint, csv_event_names)
    if related and len(related) >= 2:
        matched_labels.append(_pick_primary_csv_label(related))

    for label in csv_event_names:
        lower = label.lower()
        label_norm = normalize_token(label)
        if (
            hint_norm == label_norm
            or hint_norm in label_norm
            or label_norm in hint_norm
            or lower in combined
            or (hint and hint.lower() in lower)
        ):
            matched_labels.append(label)

    for token in extract_latin_tokens(combined):
        for label in csv_event_names:
            lower = label.lower()
            if lower == token or lower.startswith(f"{token}_") or lower.split("_", 1)[0] == token:
                if label not in matched_labels:
                    matched_labels.append(label)

    if not matched_labels:
        close = get_close_matches(hint, csv_event_names, n=3, cutoff=0.72)
        matched_labels.extend(close)

    if not matched_labels:
        return None

    best: Optional[EventResolution] = None
    best_score = -1
    seen: set[str] = set()

    for label in matched_labels:
        if label in seen:
            continue
        seen.add(label)

        score = 10
        if label.lower() in combined:
            score += 20
        if hint_norm and hint_norm in normalize_token(label):
            score += 15
        if label.lower().endswith("_entry"):
            score += 5

        canonical = _lookup_in_index(events_index, label)
        if canonical:
            score += _score_event_for_context(
                canonical, events_index, csv_event_names, query, hint
            )
            candidate = EventResolution(
                event_name=canonical,
                event_def=_event_def_from_index(events_index, canonical),
                match_method="csv_label_to_dict",
                csv_labels=(label,),
            )
        else:
            candidate = EventResolution(
                event_name=label,
                event_def=virtual_event_def(label),
                match_method="csv_virtual",
                csv_labels=(label,),
                unmapped=True,
            )

        if score > best_score:
            best_score = score
            best = candidate

    return best


def resolve_event(
    name: str,
    events_index: dict,
    *,
    csv_event_names: Optional[List[str]] = None,
    query: str = "",
) -> EventResolution:
    """解析事件名；优先字典精确匹配，歧义时用 CSV 上下文消歧，最终不因未映射而失败。"""
    hint = (name or "").strip()
    if not hint:
        raise MetadataResolverError("事件名为空")

    csv_names = list(csv_event_names or [])
    query_text = query or ""

    csv_resolved = (
        _resolve_from_csv_pool(hint, query_text, csv_names, events_index)
        if csv_names
        else None
    )

    direct = _lookup_in_index(events_index, hint)
    if direct:
        from services.event_scope import module_primary_canonical

        module_primary = module_primary_canonical(query_text or hint, csv_names, events_index)
        if module_primary and module_primary != direct:
            direct = module_primary

        dict_res = EventResolution(
            event_name=direct,
            event_def=_event_def_from_index(events_index, direct),
            match_method="dict",
            csv_labels=_csv_labels_for_event(events_index, direct, csv_names),
        )
        if csv_resolved:
            dict_score = _score_event_for_context(
                direct, events_index, csv_names, query_text, hint
            )
            csv_score = _score_event_for_context(
                csv_resolved.event_name, events_index, csv_names, query_text, hint
            )
            if csv_resolved.csv_labels:
                csv_score += 15
            if csv_score > dict_score:
                return csv_resolved
        return dict_res

    if csv_resolved:
        return csv_resolved

    if csv_names:
        prefix = hint_norm = normalize_token(hint)
        if prefix:
            prefix_hits = [
                label
                for label in csv_names
                if label.lower().startswith(prefix.split("_")[0])
                or prefix in normalize_token(label)
            ]
            if len(prefix_hits) == 1:
                only = prefix_hits[0]
                canonical = _lookup_in_index(events_index, only)
                if canonical:
                    return EventResolution(
                        event_name=canonical,
                        event_def=_event_def_from_index(events_index, canonical),
                        match_method="csv_prefix",
                        csv_labels=(only,),
                    )
                return EventResolution(
                    event_name=only,
                    event_def=virtual_event_def(only),
                    match_method="csv_virtual_prefix",
                    csv_labels=(only,),
                    unmapped=True,
                )

    event_names: List[str] = list(events_index.get("event_names", []))
    close = get_close_matches(hint, event_names, n=1, cutoff=0.72)
    if close:
        canonical = close[0]
        return EventResolution(
            event_name=canonical,
            event_def=_event_def_from_index(events_index, canonical),
            match_method="fuzzy_dict",
            csv_labels=_csv_labels_for_event(events_index, canonical, csv_names),
        )

    if csv_names:
        from services.event_scope import extract_latin_tokens, infer_related_csv_events, _pick_primary_csv_label

        related = infer_related_csv_events(query_text or hint, csv_names)
        if related:
            fallback_label = _pick_primary_csv_label(related)
        else:
            fallback_label = csv_names[0]
            for label in csv_names:
                if query_text and label.lower() in query_text.lower():
                    fallback_label = label
                    break
                for token in extract_latin_tokens(f"{query_text} {hint}"):
                    if token in label.lower():
                        fallback_label = label
                        break
        canonical = _lookup_in_index(events_index, fallback_label)
        if canonical:
            return EventResolution(
                event_name=canonical,
                event_def=_event_def_from_index(events_index, canonical),
                match_method="csv_fallback",
                csv_labels=(fallback_label,),
            )
        return EventResolution(
            event_name=fallback_label,
            event_def=virtual_event_def(fallback_label),
            match_method="csv_virtual_fallback",
            csv_labels=(fallback_label,),
            unmapped=True,
        )

    raise MetadataResolverError(f"无法解析事件 '{hint}'，且数据池中无可用 event 值")


def lookup_event(
    events_index: dict,
    event_name: str,
    *,
    csv_event_names: Optional[List[str]] = None,
    query: str = "",
) -> dict:
    """兼容旧接口：返回 event_def dict。"""
    return resolve_event(
        event_name,
        events_index,
        csv_event_names=csv_event_names,
        query=query,
    ).event_def


def repair_plan_event_fields(
    data: dict,
    events_index: dict,
    csv_event_names: List[str],
    query: str,
) -> dict:
    """兼容旧接口；委托给 LLM 优先的事件适配层。"""
    from services.event_mapping import repair_plan_event_adaptation

    return repair_plan_event_adaptation(data, events_index, csv_event_names, query)


def build_column_catalog(columns: List[str]) -> dict[str, str]:
    """CSV 列名归一化索引：normalize_token -> 实际列名。"""
    catalog: dict[str, str] = {}
    for col in columns:
        catalog[normalize_token(col)] = col
        catalog[col] = col
    return catalog


def resolve_column_name(
    target: str,
    columns: List[str],
    event_def: Optional[dict] = None,
    column_catalog: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """解析 dimension / metric 字段到 CSV 列名；字典属性名为辅，列名为辅。"""
    if not columns or not target:
        return None

    catalog = column_catalog or build_column_catalog(columns)
    target_norm = normalize_token(target)
    if target_norm in catalog:
        return catalog[target_norm]

    if event_def:
        for attr_name, meta in event_def.get("attributes", {}).items():
            candidates = [attr_name, str(meta.get("cn_name", "")).split("\n")[0], target]
            for candidate in candidates:
                candidate = candidate.strip()
                if not candidate:
                    continue
                key = normalize_token(candidate)
                if key in catalog:
                    return catalog[key]

    for col in columns:
        col_norm = normalize_token(col)
        if target_norm and (target_norm in col_norm or col_norm in target_norm):
            return col

    close = get_close_matches(target, columns, n=1, cutoff=0.75)
    if close:
        return close[0]

    return None
