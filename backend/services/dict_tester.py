"""埋点字典与 CSV 数据池的匹配测试。"""

from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Any

import pandas as pd

from config import ConfigError, ensure_data_pool_not_empty
from services.csv_processor import _find_event_column, load_data_pool
from services.data_profiler import list_distinct_csv_events
from services.field_resolver import _csv_labels_for_event

_LABEL_SPLIT = re.compile(r"[_\-/\\|]+")


def extract_csv_labels_from_event(event: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for attr in event.get("属性列表", []):
        if attr.get("事件的属性") != "eventname":
            continue
        desc = attr.get("属性值的描述")
        if isinstance(desc, list):
            for item in desc:
                if isinstance(item, dict) and item.get("label"):
                    labels.append(str(item["label"]))
        elif isinstance(desc, str) and desc.strip():
            labels.append(desc.strip())
    return list(dict.fromkeys(labels))


def _event_tokens(event_name: str) -> set[str]:
    tokens: set[str] = set()
    for part in _LABEL_SPLIT.split(event_name):
        part = part.strip().lower()
        if len(part) >= 2:
            tokens.add(part)
    compact = event_name.replace("_", "").replace(" ", "").lower()
    if compact:
        tokens.add(compact)
    return tokens


def suggest_csv_labels(
    event_name: str,
    csv_event_names: list[str],
    *,
    limit: int = 12,
) -> list[str]:
    if not csv_event_names:
        return []

    tokens = _event_tokens(event_name)
    scored: list[tuple[int, str]] = []
    for csv_name in csv_event_names:
        lower = csv_name.lower()
        score = 0
        for token in tokens:
            if token in lower:
                score += 10
        if event_name.lower() in lower or lower in event_name.lower():
            score += 15
        if score > 0:
            scored.append((score, csv_name))

    scored.sort(key=lambda item: item[0], reverse=True)
    suggestions = [name for _, name in scored[:limit]]
    if suggestions:
        return suggestions

    close = get_close_matches(event_name, csv_event_names, n=limit, cutoff=0.45)
    if close:
        return close

    normalized = event_name.replace("_", "").lower()
    pool_norm = {name.replace("_", "").lower(): name for name in csv_event_names}
    close_norm = get_close_matches(normalized, list(pool_norm.keys()), n=limit, cutoff=0.6)
    return [pool_norm[item] for item in close_norm]


def test_event_against_pool(
    event_name: str,
    events_index: dict[str, Any],
    *,
    csv_labels: list[str] | None = None,
    sample_limit: int = 5,
) -> dict[str, Any]:
    try:
        ensure_data_pool_not_empty()
    except ConfigError as exc:
        raise ValueError(str(exc)) from exc

    df = load_data_pool()
    pool_total = len(df)
    event_col = _find_event_column(list(df.columns))
    csv_pool = list_distinct_csv_events(df)

    if csv_labels is not None:
        labels = list(dict.fromkeys(v for v in csv_labels if str(v).strip()))
    else:
        labels = list(_csv_labels_for_event(events_index, event_name, csv_pool))
        if not labels:
            raw_event = events_index.get("events", {}).get(event_name, {})
            labels = extract_csv_labels_from_event(
                {"属性列表": raw_event.get("attributes", {})}
            )
            # attributes in index differ from raw - reload from events def aliases
            labels = list(
                dict.fromkeys(
                    alias
                    for alias in raw_event.get("aliases", [])
                    if str(alias) in set(csv_pool)
                )
            )

    pool_set = set(csv_pool)
    label_stats: list[dict[str, Any]] = []
    total_matched = 0

    if event_col and labels:
        series = df[event_col].astype(str)
        for label in labels:
            count = int((series == label).sum())
            label_stats.append(
                {
                    "label": label,
                    "row_count": count,
                    "in_pool": label in pool_set,
                }
            )
            total_matched += count

    sample_rows: list[dict] = []
    if event_col and labels and total_matched > 0:
        mask = df[event_col].astype(str).isin(labels)
        sample = df.loc[mask].head(sample_limit)
        sample_rows = sample.to_dict(orient="records")

    saved_labels = list(_csv_labels_for_event(events_index, event_name, csv_pool))
    suggestions = suggest_csv_labels(event_name, csv_pool) if total_matched == 0 else []

    return {
        "event_name": event_name,
        "event_column": event_col,
        "csv_labels_tested": labels,
        "saved_csv_labels": saved_labels,
        "label_stats": label_stats,
        "total_matched_rows": total_matched,
        "pool_total_rows": pool_total,
        "distinct_csv_events": len(csv_pool),
        "sample_rows": sample_rows,
        "suggested_csv_labels": suggestions,
    }
