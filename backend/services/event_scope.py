"""根据用户问题与 CSV 实际 event 列推断分析范围。"""

from __future__ import annotations

import re
from typing import List, Optional, Set

_LATIN_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")


def extract_latin_tokens(text: str) -> List[str]:
    """从中文问题中提取英文 event 前缀，如「分析carlog」→ carlog。"""
    return list(dict.fromkeys(match.lower() for match in _LATIN_TOKEN.findall(text)))


def _pick_primary_csv_label(related: Set[str]) -> str:
    """模块级问题优先选 entry 类事件作为代表。"""
    ordered = sorted(related)
    for label in ordered:
        lower = label.lower()
        if lower.endswith("_entry") or lower.endswith("entry"):
            return label
    return ordered[0]


def infer_related_csv_events(
    query: str, csv_event_names: List[str]
) -> Optional[Set[str]]:
    """用户问题较笼统且 CSV 含多个相关 event 时，返回应一并纳入过滤的值集合。"""
    if not csv_event_names or len(csv_event_names) <= 1:
        return None

    q = query.strip().lower()
    if not q:
        return None

    labels = [str(name) for name in csv_event_names]
    lower_labels = [label.lower() for label in labels]

    search_terms = [q, *extract_latin_tokens(query)]

    for term in search_terms:
        if any(term in label or label in term for label in lower_labels):
            related = {
                label
                for label in labels
                if term in label.lower() or label.lower().split("_", 1)[0] in term
            }
            if len(related) >= 2:
                return related

    prefixes: dict[str, list[str]] = {}
    for label in labels:
        head = label.lower().split("_", 1)[0]
        prefixes.setdefault(head, []).append(label)

    for term in search_terms:
        for prefix, group in prefixes.items():
            if len(group) >= 2 and (term == prefix or prefix in term or term in prefix):
                return set(group)

    return None


def module_primary_canonical(
    query: str,
    csv_event_names: List[str],
    events_index: dict,
) -> Optional[str]:
    """模块级问题返回字典 canonical 代表事件（如 carlog → Carlog_进入）。"""
    related = infer_related_csv_events(query, csv_event_names)
    if not related or len(related) < 2:
        return None

    from services.field_resolver import _lookup_in_index

    primary_label = _pick_primary_csv_label(related)
    return _lookup_in_index(events_index, primary_label)


def apply_module_anchor_event(
    data: dict,
    query: str,
    csv_event_names: List[str],
    events_index: dict,
) -> dict:
    """模块级 query 时，用数据池主事件覆盖 LLM 误选的子事件（如自动剪辑）。"""
    canonical = module_primary_canonical(query, csv_event_names, events_index)
    if not canonical:
        return data

    updated = dict(data)
    updated["matched_event"] = canonical
    module = events_index.get("events", {}).get(canonical, {}).get("module")
    if module:
        updated["matched_module"] = module
    return updated


def fallback_matched_event(
    query: str,
    csv_event_names: List[str],
    events_index: dict,
) -> Optional[str]:
    """从 CSV event 反查 canonical 名（兼容旧调用）。"""
    canonical = module_primary_canonical(query, csv_event_names, events_index)
    if canonical:
        return canonical

    if not csv_event_names:
        return None
    try:
        from services.field_resolver import resolve_event

        return resolve_event(
            query,
            events_index,
            csv_event_names=csv_event_names,
            query=query,
        ).event_name
    except Exception:
        return None
