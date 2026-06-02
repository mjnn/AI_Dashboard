"""根据用户问题与 CSV 实际 event 列推断分析范围。"""

from __future__ import annotations

import re
from typing import List, Literal, Optional, Set

ScopeMode = Literal["single_event", "event_list", "module", "comprehensive"]

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


def csv_labels_for_module(
    module_name: str,
    events_index: dict,
    csv_event_names: List[str],
) -> Set[str]:
    """字典模块下、数据池中实际存在埋点的 CSV event 取值。"""
    if not module_name:
        return set()
    from services.field_resolver import _csv_labels_for_event

    labels: Set[str] = set()
    for canonical, definition in events_index.get("events", {}).items():
        if definition.get("module") != module_name:
            continue
        labels.update(_csv_labels_for_event(events_index, canonical, csv_event_names))
    return labels


def canonical_events_for_module(
    module_name: str,
    events_index: dict,
    csv_event_names: List[str],
) -> List[str]:
    """模块内在数据池有数据的字典事件（按字典顺序）。"""
    if not module_name:
        return []
    from services.field_resolver import _csv_labels_for_event

    ordered: List[str] = []
    for module in events_index.get("modules", []):
        if module.get("name") != module_name:
            continue
        for canonical in module.get("events", []):
            if _csv_labels_for_event(events_index, canonical, csv_event_names):
                ordered.append(canonical)
        return ordered

    for canonical, definition in events_index.get("events", {}).items():
        if definition.get("module") == module_name and _csv_labels_for_event(
            events_index, canonical, csv_event_names
        ):
            ordered.append(canonical)
    return sorted(dict.fromkeys(ordered))


def infer_prefix_group_from_anchor(
    matched_event: str,
    events_index: dict,
    csv_event_names: List[str],
) -> Set[str]:
    """从锚点事件推断同前缀的一组 CSV event（如 carlog_*）。"""
    from services.event_mapping import infer_csv_filter_for_canonical

    anchor_labels = infer_csv_filter_for_canonical(
        matched_event, events_index, csv_event_names
    )
    if not anchor_labels:
        return set()

    primary = _pick_primary_csv_label(set(anchor_labels))
    prefix = primary.lower().split("_", 1)[0]
    if not prefix:
        return set(anchor_labels)

    group = {
        str(name)
        for name in csv_event_names
        if str(name).lower() == prefix or str(name).lower().startswith(f"{prefix}_")
    }
    return group if len(group) >= 2 else set(anchor_labels)


def _canonicals_for_scope(
    scope: Set[str],
    matched_event: str,
    matched_module: str | None,
    events_index: dict,
    csv_event_names: List[str],
) -> List[str]:
    canonicals: List[str] = []
    module = matched_module or events_index.get("events", {}).get(matched_event, {}).get(
        "module", ""
    )
    if module:
        from services.field_resolver import _csv_labels_for_event

        for canonical in canonical_events_for_module(
            module, events_index, csv_event_names
        ):
            labels = set(_csv_labels_for_event(events_index, canonical, csv_event_names))
            if labels & scope:
                canonicals.append(canonical)

    if len(canonicals) < 2:
        from services.field_resolver import _lookup_in_index

        for label in sorted(scope):
            canonical = _lookup_in_index(events_index, label)
            if canonical and canonical not in canonicals:
                canonicals.append(canonical)
            elif not canonical and label not in canonicals:
                canonicals.append(label)

    return canonicals


def expand_event_scope(
    *,
    scope_mode: ScopeMode = "comprehensive",
    matched_event: str,
    matched_module: str | None,
    csv_event_filter: List[str] | None,
    query: str,
    events_index: dict,
    csv_event_names: List[str],
    max_module_events: int = 20,
) -> tuple[Set[str], List[str]]:
    """
    按 scope_mode 扩展分析范围。
    single_event：仅 matched_event 对应 CSV；
    event_list：仅 plan/字典给出的列表；
    module / comprehensive：见各分支（comprehensive 为最全策略）。
    """
    from services.event_mapping import infer_csv_filter_for_canonical, sanitize_csv_event_filter

    if scope_mode == "single_event":
        labels = infer_csv_filter_for_canonical(
            matched_event, events_index, csv_event_names
        )
        scope = set(labels)
        return scope, [matched_event] if matched_event else []

    if scope_mode == "event_list":
        scope: Set[str] = set()
        if csv_event_filter:
            scope.update(sanitize_csv_event_filter(csv_event_filter, csv_event_names))
        if not scope:
            scope.update(
                infer_csv_filter_for_canonical(matched_event, events_index, csv_event_names)
            )
        return scope, _canonicals_for_scope(
            scope, matched_event, matched_module, events_index, csv_event_names
        )

    if scope_mode == "module":
        module = matched_module or events_index.get("events", {}).get(matched_event, {}).get(
            "module", ""
        )
        scope = (
            csv_labels_for_module(module, events_index, csv_event_names)
            if module
            else set()
        )
        if not scope:
            scope.update(
                infer_csv_filter_for_canonical(matched_event, events_index, csv_event_names)
            )
        canonicals = (
            canonical_events_for_module(module, events_index, csv_event_names)
            if module
            else ([matched_event] if matched_event else [])
        )
        return scope, canonicals

    return expand_comprehensive_event_scope(
        matched_event=matched_event,
        matched_module=matched_module,
        csv_event_filter=csv_event_filter,
        query=query,
        events_index=events_index,
        csv_event_names=csv_event_names,
        max_module_events=max_module_events,
    )


def expand_comprehensive_event_scope(
    *,
    matched_event: str,
    matched_module: str | None,
    csv_event_filter: List[str] | None,
    query: str,
    events_index: dict,
    csv_event_names: List[str],
    max_module_events: int = 20,
) -> tuple[Set[str], List[str]]:
    """
    扩展分析范围为全部相关事件。
    返回 (CSV 过滤集合, 有序字典 canonical 列表)。
    """
    from services.event_mapping import sanitize_csv_event_filter

    scope: Set[str] = set()
    if csv_event_filter:
        scope.update(sanitize_csv_event_filter(csv_event_filter, csv_event_names))

    module = matched_module or events_index.get("events", {}).get(matched_event, {}).get(
        "module", ""
    )

    scope.update(infer_prefix_group_from_anchor(matched_event, events_index, csv_event_names))

    related = infer_related_csv_events(query or matched_event, csv_event_names)
    if related:
        scope.update(related)

    if module:
        module_labels = csv_labels_for_module(module, events_index, csv_event_names)
        if 2 <= len(module_labels) <= max_module_events:
            scope.update(module_labels)

    if not scope:
        from services.event_mapping import infer_csv_filter_for_canonical

        scope.update(
            infer_csv_filter_for_canonical(matched_event, events_index, csv_event_names)
        )

    canonicals: List[str] = []
    if module:
        from services.field_resolver import _csv_labels_for_event

        for canonical in canonical_events_for_module(
            module, events_index, csv_event_names
        ):
            labels = set(_csv_labels_for_event(events_index, canonical, csv_event_names))
            if labels & scope:
                canonicals.append(canonical)

    if len(canonicals) < 2:
        from services.field_resolver import _lookup_in_index

        for label in sorted(scope):
            canonical = _lookup_in_index(events_index, label)
            if canonical and canonical not in canonicals:
                canonicals.append(canonical)
            elif not canonical and label not in canonicals:
                canonicals.append(label)

    return scope, canonicals


def scope_display_label(
    matched_event: str,
    matched_module: str | None,
    scope_size: int,
) -> str:
    """多事件范围的人类可读标签。"""
    if scope_size <= 1:
        return matched_event
    return f"{matched_event} 等 {scope_size} 个相关事件"
