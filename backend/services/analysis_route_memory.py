"""分析路线记忆：缓存意图/字典/可视化骨架，故事层每次可刷新。"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from config import EVENTS_DICT_PATH, data_pool_cache_key
from schemas.agent_plan import AgentContextBundle, VisualizationProposal
from services.analysis_registry import wants_comprehensive_analysis, wants_funnel_analysis, wants_usage_frequency_analysis
from services.event_scope import extract_latin_tokens

logger = logging.getLogger(__name__)

_MAX_ENTRIES = int(os.getenv("ANALYSIS_ROUTE_CACHE_MAX", "200"))
_CACHE_DIR = Path(
    os.getenv(
        "ANALYSIS_ROUTE_CACHE_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "analysis_route_cache"),
    )
)
_CACHE_FILE = _CACHE_DIR / "routes.json"

_BYPASS_PATTERN = re.compile(
    r"换个|重新分析|不要重复|别的方式|别的角度|深入挖掘|创新|发散|重来|换种",
    re.IGNORECASE,
)

_FOCUS_KEYWORDS = (
    ("漏斗", "focus:funnel"),
    ("转化", "focus:funnel"),
    ("趋势", "focus:trend"),
    ("对比", "focus:compare"),
    ("留存", "focus:retention"),
    ("活跃", "focus:active"),
    ("热力", "focus:heatmap"),
    ("分布", "focus:distribution"),
)

_MODULE_ALIASES = {
    "导航": "nav",
    "地图": "nav",
    "navi": "nav",
    "行车": "drive",
    "音乐": "music",
    "空调": "hvac",
}


def route_cache_enabled() -> bool:
    return os.getenv("ANALYSIS_ROUTE_CACHE", "true").lower() in ("1", "true", "yes")


def skip_feasibility_on_cache_hit() -> bool:
    """路线缓存命中且数据池指纹未变时，跳过 process_csv 可行性 dry-run。"""
    return os.getenv("ANALYSIS_ROUTE_SKIP_FEASIBILITY_ON_HIT", "true").lower() in (
        "1",
        "true",
        "yes",
    )


def story_always_fresh() -> bool:
    return os.getenv("ANALYSIS_STORY_ALWAYS_FRESH", "true").lower() in (
        "1",
        "true",
        "yes",
    )


def dictionary_cache_key() -> str:
    path = Path(EVENTS_DICT_PATH)
    if not path.is_file():
        return "missing"
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def should_bypass_cache(query: str, *, force_fresh: bool = False) -> bool:
    if force_fresh:
        return True
    if _BYPASS_PATTERN.search(query or ""):
        return True
    return False


def build_route_signature(query: str) -> str:
    """将自然语言问题归一化为可复用的路线签名（非逐字匹配）。"""
    q = (query or "").strip().lower()
    tokens: set[str] = set()

    if wants_comprehensive_analysis(q):
        tokens.add("scope:comprehensive")
    elif wants_usage_frequency_analysis(q):
        tokens.add("scope:usage_frequency")
    elif wants_funnel_analysis(q):
        tokens.add("scope:funnel")
    else:
        tokens.add("scope:single")

    for token in extract_latin_tokens(query):
        tokens.add(f"mod:{token}")

    for keyword, label in _FOCUS_KEYWORDS:
        if keyword in query:
            tokens.add(label)

    for alias, mod in _MODULE_ALIASES.items():
        if alias in query:
            tokens.add(f"mod:{mod}")

    if not tokens:
        tokens.add("scope:generic")

    return "|".join(sorted(tokens))


def _cache_key(signature: str, locale: str | None) -> str:
    lang = locale or "zh"
    return f"{data_pool_cache_key()}:{dictionary_cache_key()}:{lang}:{signature}"


class StoredAnalysisRoute(BaseModel):
    cache_key: str
    signature: str
    locale: str = "zh"
    context: AgentContextBundle
    proposals: List[VisualizationProposal]
    converged: bool = False
    query_samples: List[str] = Field(default_factory=list)
    hit_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    cluster_discovery: Optional[dict[str, Any]] = None


class _RouteStore(BaseModel):
    entries: dict[str, StoredAnalysisRoute] = Field(default_factory=dict)


def _load_store() -> _RouteStore:
    if not _CACHE_FILE.is_file():
        return _RouteStore()
    try:
        raw = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        return _RouteStore.model_validate(raw)
    except Exception as exc:
        logger.warning("分析路线缓存损坏，将重建: %s", exc)
        return _RouteStore()


def _save_store(store: _RouteStore) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if len(store.entries) > _MAX_ENTRIES:
        ordered = sorted(
            store.entries.items(),
            key=lambda item: item[1].updated_at,
            reverse=True,
        )
        store.entries = dict(ordered[:_MAX_ENTRIES])
    _CACHE_FILE.write_text(
        store.model_dump_json(indent=2),
        encoding="utf-8",
    )


def lookup_route(
    query: str,
    *,
    locale: str | None = None,
) -> Optional[StoredAnalysisRoute]:
    if not route_cache_enabled():
        return None
    signature = build_route_signature(query)
    key = _cache_key(signature, locale)
    store = _load_store()
    entry = store.entries.get(key)
    if entry is None:
        return None
    entry.hit_count += 1
    entry.updated_at = time.time()
    if query not in entry.query_samples:
        entry.query_samples = ([query] + entry.query_samples)[:8]
    store.entries[key] = entry
    _save_store(store)
    logger.info(
        "分析路线缓存命中 signature=%s hits=%d",
        signature,
        entry.hit_count,
    )
    return entry


def remember_route(
    query: str,
    *,
    locale: str | None,
    context: AgentContextBundle,
    proposals: List[VisualizationProposal],
    converged: bool,
) -> None:
    if not route_cache_enabled() or not converged:
        return
    signature = build_route_signature(query)
    key = _cache_key(signature, locale)
    now = time.time()
    store = _load_store()
    existing = store.entries.get(key)
    store.entries[key] = StoredAnalysisRoute(
        cache_key=key,
        signature=signature,
        locale=locale or "zh",
        context=context,
        proposals=proposals,
        converged=converged,
        query_samples=([query] + (existing.query_samples if existing else []))[:8],
        hit_count=existing.hit_count if existing else 0,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        cluster_discovery=existing.cluster_discovery if existing else None,
    )
    _save_store(store)
    logger.info("分析路线已写入缓存 signature=%s", signature)


def remember_cluster(
    query: str,
    *,
    locale: str | None,
    cluster_discovery: dict[str, Any],
) -> None:
    if not route_cache_enabled():
        return
    signature = build_route_signature(query)
    key = _cache_key(signature, locale)
    store = _load_store()
    entry = store.entries.get(key)
    if entry is None:
        return
    entry.cluster_discovery = cluster_discovery
    entry.updated_at = time.time()
    store.entries[key] = entry
    _save_store(store)


def lookup_cluster(
    query: str,
    *,
    locale: str | None = None,
) -> Optional[dict[str, Any]]:
    if not route_cache_enabled():
        return None
    signature = build_route_signature(query)
    key = _cache_key(signature, locale)
    store = _load_store()
    entry = store.entries.get(key)
    if entry and entry.cluster_discovery:
        return entry.cluster_discovery
    return None


def clear_route_cache() -> None:
    store = _RouteStore()
    _save_store(store)
    logger.info("分析路线缓存已清空")
