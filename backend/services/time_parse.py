"""CSV 时间列解析 — time 列按 UTC 存储，转换为 UTC+8（Asia/Shanghai）。"""

from __future__ import annotations

import re

import pandas as pd

_NORMALIZE = re.compile(r"[\s_\-]+")


def normalize_column_name(name: str) -> str:
    return _NORMALIZE.sub("", str(name).lower())


def is_utc_time_column(col: str | None) -> bool:
    """表头为 time（大小写不敏感）时，按 UTC 解析并转 UTC+8。"""
    if not col:
        return False
    return normalize_column_name(col) == "time"


def parse_time_values(series: pd.Series, col: str | None = None) -> pd.Series:
    """解析时间列；time 列视为 UTC，输出无时区的 UTC+8 本地时间。"""
    if is_utc_time_column(col):
        parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
        return parsed.dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    return pd.to_datetime(series, errors="coerce")
