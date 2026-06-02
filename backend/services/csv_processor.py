"""CSV 数据处理服务。"""

from __future__ import annotations

import re
import time
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from schemas.analysis import AnalysisPlan, ExecutionSummary, MetricDef
from services.time_parse import parse_time_values
from services.field_resolver import resolve_column_name
from services.analysis_registry import (
    ACTIVE_DAYS_BUCKET_DIMENSION,
    ACTIVE_USER_DIMENSION,
    COHORT_DATE_DIMENSION,
    DAY_OF_WEEK_DIMENSION,
    EVENT_NAME_DIMENSION,
    FUNNEL_STEP_DIMENSION,
    HOUR_OF_DAY_DIMENSION,
    PERCENTILE_DIMENSION,
    RETENTION_DAY_DIMENSION,
    USER_TYPE_DIMENSION,
    is_multi_event_analysis,
    is_time_dimension,
    needs_full_dataset,
    normalize_plan_for_analysis,
    uses_derived_dimension,
)


_TIME_PATTERNS = re.compile(r"date|time|timestamp|日期|时间", re.IGNORECASE)
_EVENT_PATTERNS = re.compile(r"event|事件", re.IGNORECASE)
_WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_VIN_CANDIDATES = ["vin_code", "vin", "vehicle_vin", "VIN"]


def _normalize_col(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name.lower())


def _read_csv_with_encoding(csv_path: str) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return pd.read_csv(csv_path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return pd.read_csv(csv_path)


def load_data_pool() -> pd.DataFrame:
    """读取 CSV_DATA_PATH 目录下全部 CSV 并合并为分析用 DataFrame。"""
    from config import ConfigError, list_csv_files, resolve_csv_data_dir

    csv_dir = resolve_csv_data_dir()
    files = list_csv_files()
    if not files:
        raise ConfigError(
            f"数据目录为空: {csv_dir}，请将 CSV 文件放入该目录（CSV_DATA_PATH）"
        )

    frames = [_read_csv_with_encoding(str(csv_dir / item["filename"])) for item in files]
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True, sort=False)


def _find_column(
    columns: List[str],
    target: str,
    event_def: Optional[dict] = None,
    pattern: Optional[re.Pattern[str]] = None,
) -> Optional[str]:
    """按精确名、属性映射、模式匹配查找 CSV 列。"""
    if not columns:
        return None

    resolved = resolve_column_name(target, columns, event_def)
    if resolved:
        return resolved

    normalized_map = {_normalize_col(col): col for col in columns}

    target_norm = _normalize_col(target)
    if target_norm in normalized_map:
        return normalized_map[target_norm]

    if event_def:
        attributes: dict = event_def.get("attributes", {})
        for attr_name, meta in attributes.items():
            cn_name = str(meta.get("cn_name", ""))
            candidates = [attr_name, cn_name, target]
            for candidate in candidates:
                candidate_norm = _normalize_col(candidate)
                if candidate_norm in normalized_map:
                    return normalized_map[candidate_norm]
                for col in columns:
                    if candidate_norm and candidate_norm in _normalize_col(col):
                        return col

    for col in columns:
        col_norm = _normalize_col(col)
        if target_norm and (target_norm in col_norm or col_norm in target_norm):
            return col

    if pattern:
        for col in columns:
            if pattern.search(col):
                return col

    return None


def _find_time_column(columns: List[str]) -> Optional[str]:
    for col in columns:
        if _TIME_PATTERNS.search(col):
            return col
    return None


def _find_event_column(columns: List[str]) -> Optional[str]:
    for col in columns:
        if _EVENT_PATTERNS.search(col):
            return col
    return None


def _apply_time_filter(df: pd.DataFrame, time_col: str, plan: AnalysisPlan) -> pd.DataFrame:
    series = parse_time_values(df[time_col], time_col)
    valid = series.notna()
    if not valid.any():
        return df.iloc[0:0].copy()

    filtered = df.loc[valid].copy()
    filtered["_parsed_time"] = series.loc[valid]

    time_range = plan.time_range
    if time_range.type == "last_n_days" and time_range.value:
        max_date = filtered["_parsed_time"].max()
        start = max_date - timedelta(days=time_range.value)
        filtered = filtered[filtered["_parsed_time"] >= start]
    elif time_range.type == "date_range":
        if time_range.start:
            start = pd.to_datetime(time_range.start)
            filtered = filtered[filtered["_parsed_time"] >= start]
        if time_range.end:
            end = pd.to_datetime(time_range.end)
            filtered = filtered[filtered["_parsed_time"] <= end]

    return filtered


def _normalize_dimension(df: pd.DataFrame, dim_col: str, dimension: str) -> pd.DataFrame:
    result = df.copy()
    if dimension == "date" or _TIME_PATTERNS.search(dimension):
        result[dimension] = parse_time_values(result[dim_col], dim_col).dt.date
    else:
        result[dimension] = result[dim_col]
    return result


_SAFE_FORMULA_PATTERN = re.compile(r"^[a-zA-Z0-9_\s+\-*/().]+$")


def _compute_formula(df: pd.DataFrame, metric: MetricDef) -> pd.Series:
    if not metric.formula or not _SAFE_FORMULA_PATTERN.match(metric.formula):
        return pd.Series([pd.NA] * len(df), index=df.index)

    expr = metric.formula
    local_vars: Dict[str, pd.Series] = {}
    for col in df.columns:
        if col in expr:
            local_vars[col] = pd.to_numeric(df[col], errors="coerce")

    if metric.formula_components:
        for component in metric.formula_components:
            if component in df.columns:
                local_vars[component] = pd.to_numeric(df[component], errors="coerce")

    try:
        return pd.eval(expr, local_dict=local_vars, engine="python")
    except Exception:
        return pd.Series([pd.NA] * len(df), index=df.index)


def _aggregate(
    df: pd.DataFrame,
    group_cols: List[str],
    metrics: List[MetricDef],
) -> pd.DataFrame:
    if df.empty:
        columns = group_cols + [metric.id for metric in metrics]
        return pd.DataFrame(columns=columns)

    grouped = df.groupby(group_cols, dropna=False)
    formula_metrics = [m for m in metrics if m.type == "formula"]
    aggregated: Optional[pd.DataFrame] = None

    for metric in metrics:
        if metric.type == "count":
            part = grouped.size().reset_index(name=metric.id)
        elif metric.type == "nunique" and metric.field and metric.field in df.columns:
            part = grouped[metric.field].nunique().reset_index(name=metric.id)
        elif metric.type == "formula":
            continue
        else:
            continue

        aggregated = part if aggregated is None else aggregated.merge(
            part, on=group_cols, how="outer"
        )

    if aggregated is None:
        aggregated = grouped.size().reset_index(name="_rows").drop(columns=["_rows"])

    for metric in formula_metrics:
        aggregated[metric.id] = _compute_formula(aggregated, metric)

    return aggregated


def _is_time_dimension(dimension: str) -> bool:
    return dimension == "date" or bool(_TIME_PATTERNS.search(dimension))


def _parsed_time_series(filtered: pd.DataFrame, time_col: Optional[str]) -> Optional[pd.Series]:
    if filtered.empty:
        return None
    if "_parsed_time" in filtered.columns:
        return filtered["_parsed_time"]
    if time_col and time_col in filtered.columns:
        return parse_time_values(filtered[time_col], time_col)
    return None


def _resolve_date_bounds(
    plan: AnalysisPlan,
    filtered: pd.DataFrame,
    time_col: Optional[str],
) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    series = _parsed_time_series(filtered, time_col)
    if series is None:
        return None, None

    valid = series.dropna()
    if valid.empty:
        return None, None

    max_date = valid.max().normalize()
    min_date = valid.min().normalize()
    time_range = plan.time_range

    if time_range.type == "last_n_days" and time_range.value:
        start = max_date - timedelta(days=time_range.value)
        end = max_date
    elif time_range.type == "date_range":
        start = (
            pd.to_datetime(time_range.start).normalize()
            if time_range.start
            else min_date
        )
        end = (
            pd.to_datetime(time_range.end).normalize()
            if time_range.end
            else max_date
        )
    else:
        start, end = min_date, max_date

    return start, end


def _granularity_freq(granularity: str) -> str:
    if granularity == "hourly":
        return "h"
    if granularity == "weekly":
        return "W-MON"
    return "D"


def _fill_continuous_time_axis(
    result: pd.DataFrame,
    plan: AnalysisPlan,
    filtered: pd.DataFrame,
    time_col: Optional[str],
) -> pd.DataFrame:
    """补全时间维度上的空缺，使图表时间轴连续。"""
    if result.empty or not _is_time_dimension(plan.dimension):
        return result
    if plan.sub_dimension:
        return result

    start, end = _resolve_date_bounds(plan, filtered, time_col)
    if start is None or end is None:
        return result

    freq = _granularity_freq(plan.statistical_caliber.time_granularity)
    full_index = pd.date_range(start=start, end=end, freq=freq)
    if len(full_index) == 0:
        return result

    metric_cols = [metric.id for metric in plan.metrics]
    working = result.copy()
    working[plan.dimension] = pd.to_datetime(working[plan.dimension], errors="coerce")
    working = working.dropna(subset=[plan.dimension]).set_index(plan.dimension)

    filled = working.reindex(full_index)
    for col in metric_cols:
        if col in filled.columns:
            filled[col] = pd.to_numeric(filled[col], errors="coerce").fillna(0)

    filled = filled.reset_index()
    dim_col = filled.columns[0]
    if dim_col != plan.dimension:
        filled = filled.rename(columns={dim_col: plan.dimension})

    if freq == "D":
        filled[plan.dimension] = pd.to_datetime(filled[plan.dimension]).dt.date
    else:
        filled[plan.dimension] = pd.to_datetime(filled[plan.dimension])

    output_cols = [plan.dimension] + [col for col in metric_cols if col in filled.columns]
    return filled[output_cols]


def _resolve_vin_column(
    plan: AnalysisPlan,
    columns: List[str],
    event_def: Optional[dict],
) -> Optional[str]:
    for metric in plan.metrics:
        if metric.field:
            matched = _find_column(columns, metric.field, event_def)
            if matched:
                return matched
    for candidate in _VIN_CANDIDATES:
        matched = _find_column(columns, candidate, event_def)
        if matched:
            return matched
    return None


def _usage_bucket_label(count: int) -> str:
    if count == 1:
        return "使用1次"
    if count == 2:
        return "使用2次"
    return f"使用{count}次"


def _usage_count_from_bucket_label(label: str) -> int:
    match = re.match(r"使用(\d+)次", str(label))
    return int(match.group(1)) if match else 0


def _active_days_sort_key(label: str) -> int:
    text = str(label)
    if text == "活跃10天以上":
        return 11
    match = re.match(r"活跃(\d+)天", text)
    return int(match.group(1)) if match else 999


def _aggregate_usage_buckets(
    df: pd.DataFrame,
    vin_col: str,
    plan: AnalysisPlan,
    *,
    retention_only: bool = False,
) -> pd.DataFrame:
    """按 VIN 使用次数分桶，统计各桶内车辆数（留存/频次分析）。"""
    usage = df.groupby(vin_col).size().reset_index(name="_usage_count")
    usage["_bucket"] = usage["_usage_count"].map(_usage_bucket_label)

    if retention_only:
        usage = usage[usage["_usage_count"].isin([1, 2])]

    bucket_counts = (
        usage.groupby("_bucket").size().reset_index(name="_vehicle_count")
    )
    bucket_order = usage.drop_duplicates(subset="_bucket").set_index("_bucket")["_usage_count"]
    bucket_counts["_sort"] = bucket_counts["_bucket"].map(bucket_order)
    bucket_counts = bucket_counts.sort_values("_sort")
    bucket_counts = bucket_counts.rename(columns={"_bucket": plan.dimension})
    metric_id = plan.metrics[0].id if plan.metrics else "vehicle_count"
    result = bucket_counts.rename(columns={"_vehicle_count": metric_id})
    return result[[plan.dimension, metric_id]]


def _aggregate_summary_kpi(
    df: pd.DataFrame,
    plan: AnalysisPlan,
    columns: List[str],
    event_def: Optional[dict],
) -> pd.DataFrame:
    """不分组，输出整体 KPI 汇总。"""
    row: Dict[str, object] = {}
    for metric in plan.metrics:
        if metric.type == "count":
            row[metric.id] = len(df)
        elif metric.type == "nunique" and metric.field:
            matched = _find_column(columns, metric.field, event_def)
            if matched and matched in df.columns:
                row[metric.id] = df[matched].nunique()
            else:
                row[metric.id] = pd.NA
        elif metric.type == "formula":
            row[metric.id] = pd.NA
    return pd.DataFrame([row])


def _resolve_dimension_column(
    plan: AnalysisPlan,
    columns: List[str],
    event_def: Optional[dict],
    time_col: Optional[str],
) -> Optional[str]:
    """根据 analysis_type 解析主维度对应的 CSV 列。"""
    analysis_type = plan.analysis_type or "dimension_breakdown"

    if uses_derived_dimension(analysis_type):
        return None

    if analysis_type in ("time_series", "growth_rate", "first_touch_trend", "heatmap_time") or (
        analysis_type in ("penetration", "cross_dimension", "event_comparison")
        and is_time_dimension(plan.dimension)
    ):
        if time_col:
            return time_col
        return _find_column(columns, plan.dimension, event_def, pattern=_TIME_PATTERNS)

    return _find_column(columns, plan.dimension, event_def)


def _event_name_variants(event_name: str) -> set[str]:
    values = {event_name, event_name.replace("_", ""), event_name.replace("_", " ")}
    return {v for v in values if v}


def _event_match_values(plan: AnalysisPlan, event_def: Optional[dict]) -> set[str]:
    """构建 CSV 事件列可匹配的值集合（含别名与归一化形式）。"""
    values = {plan.matched_event}
    if event_def:
        values.add(str(event_def.get("event_name", plan.matched_event)))
        for alias in event_def.get("aliases", []):
            values.add(str(alias))
        for attr_meta in event_def.get("attributes", {}).values():
            desc = attr_meta.get("description")
            if isinstance(desc, list):
                for item in desc:
                    if isinstance(item, dict) and item.get("label"):
                        values.add(str(item["label"]))
    expanded: set[str] = set()
    for value in values:
        expanded.update(_event_name_variants(value))
    return expanded


def _collect_event_filter_values(plan: AnalysisPlan, event_def: Optional[dict]) -> set[str]:
    if is_multi_event_analysis(plan.analysis_type or "") and plan.comparison_events:
        values: set[str] = set()
        for event_name in plan.comparison_events:
            values.update(_event_name_variants(event_name))
        values.update(_event_match_values(plan, event_def))
        return values
    return _event_match_values(plan, event_def)


def _ensure_parsed_time(df: pd.DataFrame, time_col: Optional[str]) -> pd.DataFrame:
    if "_parsed_time" in df.columns or not time_col:
        return df
    result = df.copy()
    result["_parsed_time"] = parse_time_values(result[time_col], time_col)
    return result


def _aggregate_period_pattern(
    df: pd.DataFrame,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    unit = plan.period_unit or "hour"
    metric_id = plan.metrics[0].id if plan.metrics else "pv"

    if unit == "weekday":
        working[plan.dimension] = working["_parsed_time"].dt.weekday.map(
            lambda i: _WEEKDAY_LABELS[i]
        )
    else:
        working[plan.dimension] = working["_parsed_time"].dt.hour.map(
            lambda h: f"{h:02d}:00"
        )

    grouped = working.groupby(plan.dimension, dropna=False).size().reset_index(name=metric_id)
    if unit == "weekday":
        order = {label: idx for idx, label in enumerate(_WEEKDAY_LABELS)}
        grouped["_order"] = grouped[plan.dimension].map(order)
        grouped = grouped.sort_values("_order").drop(columns=["_order"])
    else:
        grouped = grouped.sort_values(plan.dimension)
    return grouped.reset_index(drop=True)


def _aggregate_new_vs_returning(
    filtered: pd.DataFrame,
    full_event_df: pd.DataFrame,
    vin_col: str,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    metric_id = plan.metrics[0].id if plan.metrics else "vehicle_count"
    full = _ensure_parsed_time(full_event_df, time_col)
    filtered_w = _ensure_parsed_time(filtered, time_col)

    if "_parsed_time" not in full.columns:
        return pd.DataFrame()

    first_seen = full.groupby(vin_col)["_parsed_time"].min()
    window_start = filtered_w["_parsed_time"].min()

    vins_in_window = filtered_w[vin_col].unique()
    labels: List[str] = []
    for vin in vins_in_window:
        if vin not in first_seen.index:
            continue
        labels.append("新用户" if first_seen[vin] >= window_start else "老用户")

    if not labels:
        return pd.DataFrame(columns=[plan.dimension, metric_id])

    counts = pd.Series(labels).value_counts().reset_index()
    counts.columns = [plan.dimension, metric_id]
    return counts


def _aggregate_repeat_rate(
    df: pd.DataFrame,
    vin_col: str,
    plan: AnalysisPlan,
) -> pd.DataFrame:
    usage = df.groupby(vin_col).size()
    total = len(usage)
    repeat_users = int((usage >= 2).sum())
    rate = round(repeat_users / total * 100, 2) if total else 0.0
    metric_id = plan.metrics[0].id if plan.metrics else "repeat_rate"
    return pd.DataFrame([{
        metric_id: rate,
        "repeat_users": repeat_users,
        "total_users": total,
    }])


def _aggregate_cohort_retention(
    df: pd.DataFrame,
    vin_col: str,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    cohort_days = plan.cohort_retention_days or [1, 3, 7, 14, 30]
    sub_dim = plan.sub_dimension or RETENTION_DAY_DIMENSION
    metric_id = plan.metrics[0].id if plan.metrics else "retention_rate"

    first_seen = working.groupby(vin_col)["_parsed_time"].min().dt.normalize()
    activity = working.groupby([vin_col, working["_parsed_time"].dt.normalize().rename("_day")]).size().reset_index()[
        [vin_col, "_day"]
    ]

    rows: List[dict] = []
    for cohort_ts, cohort_vins in first_seen.groupby(first_seen):
        cohort_date = cohort_ts.date()
        cohort_set = {str(v) for v in cohort_vins.index}
        cohort_size = len(cohort_set)
        if cohort_size == 0:
            continue

        for day in cohort_days:
            check_day = cohort_ts + timedelta(days=day)
            active_vins = {
                str(v)
                for v in activity.loc[activity["_day"] == check_day, vin_col]
            }
            retained = len(cohort_set & active_vins)
            rate = round(retained / cohort_size * 100, 2)
            rows.append({
                plan.dimension: cohort_date,
                sub_dim: f"D+{day}",
                metric_id: rate,
                "retained_users": retained,
                "cohort_size": cohort_size,
            })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values([plan.dimension, sub_dim]).reset_index(drop=True)
    return result


def _aggregate_funnel(
    df: pd.DataFrame,
    event_col: str,
    vin_col: str,
    plan: AnalysisPlan,
) -> pd.DataFrame:
    steps = plan.comparison_events or [plan.matched_event]
    if len(steps) < 2:
        steps = [plan.matched_event, *(plan.comparison_events or [])]

    metric_count = "user_count"
    metric_rate = "conversion_rate"
    rows: List[dict] = []
    prev_count = 0

    for idx, step in enumerate(steps):
        step_values = _event_name_variants(step)
        step_df = df[df[event_col].astype(str).isin(step_values)]
        count = step_df[vin_col].nunique()
        rate = 100.0 if idx == 0 else (round(count / prev_count * 100, 2) if prev_count else 0.0)
        rows.append({
            plan.dimension: f"Step{idx + 1}: {step}",
            metric_count: count,
            metric_rate: rate,
        })
        prev_count = count

    return pd.DataFrame(rows)


def _aggregate_event_comparison(
    df: pd.DataFrame,
    event_col: str,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    events = plan.comparison_events or [plan.matched_event]
    working = df.copy()
    working[EVENT_NAME_DIMENSION] = working[event_col].astype(str)

    if is_time_dimension(plan.dimension) and time_col:
        working = _ensure_parsed_time(working, time_col)
        working[plan.dimension] = working["_parsed_time"].dt.date
        group_cols = [plan.dimension, plan.sub_dimension or EVENT_NAME_DIMENSION]
    else:
        group_cols = [plan.dimension]

    event_filter = set()
    for ev in events:
        event_filter.update(_event_name_variants(ev))
    working = working[working[EVENT_NAME_DIMENSION].isin(event_filter)]

    if plan.sub_dimension == EVENT_NAME_DIMENSION or EVENT_NAME_DIMENSION in group_cols:
        working[EVENT_NAME_DIMENSION] = working[EVENT_NAME_DIMENSION]

    return _aggregate(working, group_cols, plan.metrics)


def _aggregate_active_users(
    df: pd.DataFrame,
    vin_col: str,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    max_time = working["_parsed_time"].max().normalize()
    dau = working.loc[working["_parsed_time"].dt.normalize() == max_time, vin_col].nunique()
    wau = working.loc[working["_parsed_time"] >= max_time - timedelta(days=6), vin_col].nunique()
    mau = working.loc[working["_parsed_time"] >= max_time - timedelta(days=29), vin_col].nunique()

    return pd.DataFrame([
        {plan.dimension: "DAU", "uv": dau},
        {plan.dimension: "WAU", "uv": wau},
        {plan.dimension: "MAU", "uv": mau},
    ])


def _aggregate_growth_rate(
    df: pd.DataFrame,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    working[plan.dimension] = working["_parsed_time"].dt.date
    base = _aggregate(working, [plan.dimension], plan.metrics)
    base = _fill_continuous_time_axis(base, plan, df, time_col)

    value_col = plan.metrics[0].id if plan.metrics else "uv"
    if value_col not in base.columns:
        return base

    base["growth_rate"] = pd.to_numeric(base[value_col], errors="coerce").pct_change() * 100
    base["growth_rate"] = base["growth_rate"].round(2)
    return base


def _aggregate_stickiness(
    df: pd.DataFrame,
    vin_col: str,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    max_time = working["_parsed_time"].max().normalize()
    dau = working.loc[working["_parsed_time"].dt.normalize() == max_time, vin_col].nunique()
    mau = working.loc[working["_parsed_time"] >= max_time - timedelta(days=29), vin_col].nunique()
    stickiness = round(dau / mau * 100, 2) if mau else 0.0
    metric_id = plan.metrics[0].id if plan.metrics else "stickiness"

    return pd.DataFrame([{metric_id: stickiness, "dau": dau, "mau": mau}])


def _aggregate_percentile_stats(
    df: pd.DataFrame,
    vin_col: str,
    plan: AnalysisPlan,
) -> pd.DataFrame:
    usage = df.groupby(vin_col).size()
    metric_id = plan.metrics[0].id if plan.metrics else "usage_count"
    percentiles = [50, 75, 90, 99]
    rows = [
        {plan.dimension: f"P{p}", metric_id: float(usage.quantile(p / 100))}
        for p in percentiles
    ]
    return pd.DataFrame(rows)


def _aggregate_active_days_distribution(
    df: pd.DataFrame,
    vin_col: str,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    days_active = working.groupby(vin_col)["_parsed_time"].apply(
        lambda s: s.dt.normalize().nunique()
    )
    buckets = days_active.map(lambda d: f"活跃{d}天" if d <= 10 else "活跃10天以上")
    metric_id = plan.metrics[0].id if plan.metrics else "vehicle_count"
    result = buckets.value_counts().reset_index()
    result.columns = [plan.dimension, metric_id]
    result["_sort"] = result[plan.dimension].map(_active_days_sort_key)
    return result.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)


def _aggregate_heatmap_time(
    df: pd.DataFrame,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    sub_dim = plan.sub_dimension or HOUR_OF_DAY_DIMENSION
    working[plan.dimension] = working["_parsed_time"].dt.date
    working[sub_dim] = working["_parsed_time"].dt.hour.map(lambda h: f"{h:02d}:00")
    metric_id = plan.metrics[0].id if plan.metrics else "pv"
    grouped = working.groupby([plan.dimension, sub_dim], dropna=False).size().reset_index(name=metric_id)
    return grouped.sort_values([plan.dimension, sub_dim]).reset_index(drop=True)


def _aggregate_first_touch_trend(
    full_event_df: pd.DataFrame,
    vin_col: str,
    time_col: Optional[str],
    plan: AnalysisPlan,
) -> pd.DataFrame:
    working = _ensure_parsed_time(full_event_df, time_col)
    if "_parsed_time" not in working.columns:
        return pd.DataFrame()

    first_seen = working.groupby(vin_col)["_parsed_time"].min().dt.date
    metric_id = plan.metrics[0].id if plan.metrics else "new_users"
    result = first_seen.value_counts().sort_index().reset_index()
    result.columns = [plan.dimension, metric_id]
    if result.empty:
        return result
    return _fill_continuous_time_axis(result, plan, working, time_col)


def _apply_top_n(result: pd.DataFrame, plan: AnalysisPlan) -> pd.DataFrame:
    if result.empty or not plan.top_n:
        return result
    metric_col = plan.metrics[0].id if plan.metrics else result.columns[-1]
    if metric_col not in result.columns:
        return result
    return result.nlargest(plan.top_n, metric_col).reset_index(drop=True)


def _finish(
    result: pd.DataFrame,
    *,
    start_ms: float,
    unavailable: List[str],
    total_rows: int,
    filtered_rows: int,
) -> Tuple[pd.DataFrame, ExecutionSummary]:
    elapsed = int((time.perf_counter() - start_ms) * 1000)
    status = "partial" if unavailable else "success"
    return result, ExecutionSummary(
        status=status,
        unavailable_dimensions=unavailable,
        total_rows=total_rows,
        filtered_rows=filtered_rows,
        execution_time_ms=elapsed,
    )


def process_csv(
    plan: AnalysisPlan,
    event_def: Optional[dict],
    csv_path: str | None = None,
    *,
    df: pd.DataFrame | None = None,
    event_filter_override: Optional[set[str]] = None,
) -> Tuple[pd.DataFrame, ExecutionSummary]:
    """按分析计划过滤并聚合数据；未传 df 时从 csv_path 或数据池加载。"""
    start_ms = time.perf_counter()
    unavailable_dimensions: List[str] = []
    plan = normalize_plan_for_analysis(plan)
    analysis_type = plan.analysis_type or "dimension_breakdown"

    if df is None:
        if csv_path:
            df = _read_csv_with_encoding(csv_path)
        else:
            df = load_data_pool()
    total_rows = len(df)
    columns = list(df.columns)

    event_col = _find_event_column(columns)
    if event_col is None:
        elapsed = int((time.perf_counter() - start_ms) * 1000)
        return pd.DataFrame(), ExecutionSummary(
            status="failed",
            unavailable_dimensions=[],
            total_rows=total_rows,
            filtered_rows=0,
            execution_time_ms=elapsed,
        )

    time_col = _find_time_column(columns)
    vin_col = _resolve_vin_column(plan, columns, event_def)

    dim_col = _resolve_dimension_column(plan, columns, event_def, time_col)
    derived_dimension = uses_derived_dimension(analysis_type)
    if dim_col is None and not derived_dimension:
        unavailable_dimensions.append(plan.dimension)

    sub_dim_col: Optional[str] = None
    if plan.sub_dimension and plan.sub_dimension not in (
        EVENT_NAME_DIMENSION,
        HOUR_OF_DAY_DIMENSION,
        RETENTION_DAY_DIMENSION,
    ):
        sub_dim_col = _find_column(columns, plan.sub_dimension, event_def)
        if sub_dim_col is None:
            unavailable_dimensions.append(plan.sub_dimension)

    for metric in plan.metrics:
        if metric.type == "nunique" and metric.field:
            matched = _find_column(columns, metric.field, event_def)
            if matched is None and metric.field not in unavailable_dimensions:
                unavailable_dimensions.append(metric.field)

    event_values = _collect_event_filter_values(plan, event_def)
    if event_filter_override:
        event_values = event_filter_override
    event_filtered = df[df[event_col].astype(str).isin(event_values)].copy()

    if needs_full_dataset(analysis_type):
        full_event_df = event_filtered.copy()
    else:
        full_event_df = event_filtered.copy()

    filtered = event_filtered.copy()
    if time_col and not filtered.empty:
        filtered = _apply_time_filter(filtered, time_col, plan)

    for field_name, col_name in plan.filters.items():
        matched_filter_col = _find_column(columns, field_name, event_def)
        if matched_filter_col is None:
            if field_name not in unavailable_dimensions:
                unavailable_dimensions.append(field_name)
            continue
        filtered = filtered[filtered[matched_filter_col].astype(str) == str(col_name)]

    filtered_rows = len(filtered)
    if filtered_rows == 0:
        elapsed = int((time.perf_counter() - start_ms) * 1000)
        return pd.DataFrame(), ExecutionSummary(
            status="partial",
            unavailable_dimensions=unavailable_dimensions,
            total_rows=total_rows,
            filtered_rows=0,
            execution_time_ms=elapsed,
        )

    result: pd.DataFrame

    # --- 内置衍生维度分析 ---
    if analysis_type in ("usage_retention", "usage_distribution"):
        if vin_col is None:
            unavailable_dimensions.append("vin_code")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_usage_buckets(
            filtered, vin_col, plan,
            retention_only=analysis_type == "usage_retention",
        )

    elif analysis_type == "active_days_distribution":
        if vin_col is None or time_col is None:
            if vin_col is None:
                unavailable_dimensions.append("vin_code")
            if time_col is None:
                unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_active_days_distribution(filtered, vin_col, time_col, plan)

    elif analysis_type == "summary_kpi":
        result = _aggregate_summary_kpi(filtered, plan, columns, event_def)

    elif analysis_type == "period_pattern":
        if time_col is None:
            unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_period_pattern(filtered, time_col, plan)

    elif analysis_type == "new_vs_returning":
        if vin_col is None or time_col is None:
            if vin_col is None:
                unavailable_dimensions.append("vin_code")
            if time_col is None:
                unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_new_vs_returning(filtered, full_event_df, vin_col, time_col, plan)

    elif analysis_type == "repeat_rate":
        if vin_col is None:
            unavailable_dimensions.append("vin_code")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_repeat_rate(filtered, vin_col, plan)

    elif analysis_type == "cohort_retention":
        if vin_col is None or time_col is None:
            if vin_col is None:
                unavailable_dimensions.append("vin_code")
            if time_col is None:
                unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_cohort_retention(full_event_df, vin_col, time_col, plan)

    elif analysis_type == "funnel":
        if vin_col is None:
            unavailable_dimensions.append("vin_code")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_funnel(filtered, event_col, vin_col, plan)

    elif analysis_type == "event_comparison":
        result = _aggregate_event_comparison(filtered, event_col, time_col, plan)

    elif analysis_type == "active_users":
        if vin_col is None or time_col is None:
            if vin_col is None:
                unavailable_dimensions.append("vin_code")
            if time_col is None:
                unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_active_users(filtered, vin_col, time_col, plan)

    elif analysis_type == "growth_rate":
        if time_col is None:
            unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_growth_rate(filtered, time_col, plan)

    elif analysis_type == "stickiness":
        if vin_col is None or time_col is None:
            if vin_col is None:
                unavailable_dimensions.append("vin_code")
            if time_col is None:
                unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_stickiness(filtered, vin_col, time_col, plan)

    elif analysis_type == "percentile_stats":
        if vin_col is None:
            unavailable_dimensions.append("vin_code")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_percentile_stats(filtered, vin_col, plan)

    elif analysis_type == "heatmap_time":
        if time_col is None:
            unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_heatmap_time(filtered, time_col, plan)

    elif analysis_type == "first_touch_trend":
        if vin_col is None or time_col is None:
            if vin_col is None:
                unavailable_dimensions.append("vin_code")
            if time_col is None:
                unavailable_dimensions.append("date")
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )
        result = _aggregate_first_touch_trend(full_event_df, vin_col, time_col, plan)

    else:
        # dimension_breakdown / top_n_ranking / time_series / penetration / cross_dimension
        if dim_col is None:
            return _finish(
                pd.DataFrame(), start_ms=start_ms, unavailable=unavailable_dimensions,
                total_rows=total_rows, filtered_rows=filtered_rows,
            )

        working = _normalize_dimension(filtered, dim_col, plan.dimension)
        for metric in plan.metrics:
            if metric.type == "nunique" and metric.field:
                matched = _find_column(columns, metric.field, event_def)
                if matched and matched != metric.field:
                    working[metric.field] = working[matched]

        group_cols = [plan.dimension]
        if sub_dim_col is not None and plan.sub_dimension:
            working[plan.sub_dimension] = working[sub_dim_col]
            group_cols.append(plan.sub_dimension)

        result = _aggregate(working, group_cols, plan.metrics)

        if analysis_type in ("time_series", "penetration") and is_time_dimension(plan.dimension):
            result = _fill_continuous_time_axis(result, plan, filtered, time_col)

        if analysis_type == "top_n_ranking":
            result = _apply_top_n(result, plan)

        if plan.dimension in result.columns:
            result = result.sort_values(by=plan.dimension).reset_index(drop=True)

    return _finish(
        result,
        start_ms=start_ms,
        unavailable=unavailable_dimensions,
        total_rows=total_rows,
        filtered_rows=filtered_rows,
    )
