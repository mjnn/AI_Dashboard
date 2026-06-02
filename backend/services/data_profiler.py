"""CSV 数据画像 — 为 LLM 分析推荐提供结构化摘要。"""

from __future__ import annotations

import re
from typing import Any, List, Optional

import pandas as pd

from services.csv_processor import (
    _find_event_column,
    _find_time_column,
    load_data_pool,
)
from services.exploratory_analyzer import detect_feasible_analysis_types

_TIME_COL_PATTERN = re.compile(r"date|time|timestamp|日期|时间", re.I)
_EVENT_COL_PATTERN = re.compile(r"event|事件", re.I)
_VIN_COL_PATTERN = re.compile(r"vin", re.I)


def _find_vin_column(columns: List[str]) -> Optional[str]:
    for col in columns:
        if "vin" in col.lower():
            return col
    return None


def build_data_profile(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """读取数据池并生成供 LLM 使用的数据画像。"""
    if df is None:
        df = load_data_pool()
    columns = list(df.columns)
    total_rows = len(df)

    time_col = _find_time_column(columns)
    event_col = _find_event_column(columns)
    vin_col = _find_vin_column(columns)

    profile: dict[str, Any] = {
        "columns": columns,
        "total_rows": total_rows,
        "feasible_analysis_types": sorted(detect_feasible_analysis_types(columns)),
    }

    if time_col:
        parsed = pd.to_datetime(df[time_col], errors="coerce")
        valid = parsed.notna()
        if valid.any():
            profile["date_range"] = {
                "start": str(parsed.loc[valid].min().date()),
                "end": str(parsed.loc[valid].max().date()),
                "span_days": int((parsed.loc[valid].max() - parsed.loc[valid].min()).days) + 1,
            }
            daily = (
                df.loc[valid]
                .assign(_day=parsed.loc[valid].dt.date)
                .groupby("_day")
                .size()
                .sort_values(ascending=False)
            )
            profile["daily_volume"] = {
                "avg": round(float(daily.mean()), 1),
                "max_day": str(daily.index[0]),
                "max_count": int(daily.iloc[0]),
            }

    if event_col:
        event_counts = df[event_col].astype(str).value_counts()
        top_events = [
            {"name": str(name), "count": int(count)}
            for name, count in event_counts.head(8).items()
        ]
        profile["events"] = top_events
        profile["event_count"] = int(event_counts.shape[0])

    if vin_col:
        profile["unique_vins"] = int(df[vin_col].nunique())
        if time_col and event_col:
            per_vin = df.groupby(vin_col).size()
            profile["usage_per_vin"] = {
                "avg": round(float(per_vin.mean()), 2),
                "max": int(per_vin.max()),
                "median": round(float(per_vin.median()), 1),
            }

    extra_dims = [
        c
        for c in columns
        if c not in {time_col, event_col, vin_col}
        and not (
            _TIME_COL_PATTERN.search(c)
            or _EVENT_COL_PATTERN.search(c)
            or _VIN_COL_PATTERN.search(c)
        )
    ]
    if extra_dims:
        profile["extra_dimensions"] = extra_dims

    return profile


def list_distinct_csv_events(df: pd.DataFrame | None = None) -> list[str]:
    """读取数据池中 event 列的去重取值。"""
    if df is None:
        df = load_data_pool()
    event_col = _find_event_column(list(df.columns))
    if not event_col:
        return []
    return sorted(df[event_col].astype(str).unique().tolist())
