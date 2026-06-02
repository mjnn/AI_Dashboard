"""LLM 事件聚类与综合分析场景挖掘 — 代码侧仅做约束与修正。"""

from __future__ import annotations

import json
import re
from typing import List, Literal, Optional, Set

from openai import APIConnectionError, APITimeoutError, APIStatusError
from pydantic import BaseModel, Field, ValidationError

from schemas.analysis import AnalysisPlan
from services.event_mapping import (
    build_dict_csv_mapping_hint,
    sanitize_csv_event_filter,
)
from services.event_scope import infer_related_csv_events, scope_display_label
from services.field_resolver import _lookup_in_index
from services.llm_settings import get_deepseek_model
from services.llm_planner import (
    LLMApiError,
    MissingApiKeyError,
    _create_client,
    _parse_llm_json,
)

REQUEST_TIMEOUT_SECONDS = 18.0
_JSON_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)


class EventCluster(BaseModel):
    """一组语义相关、应合并分析的事件。"""

    id: str = Field(min_length=1, max_length=48)
    name: str = Field(min_length=2, max_length=60, description="聚类主题名")
    rationale: str = Field(min_length=4, max_length=300, description="为何归为一组")
    csv_events: List[str] = Field(min_length=1, description="CSV event 列取值")
    funnel_order: Optional[List[str]] = Field(
        default=None,
        description="若存在转化链路，按顺序列出 CSV event（须属于 csv_events）",
    )
    analysis_angles: List[str] = Field(
        default_factory=list,
        description="建议深挖的分析角度（自然语言）",
    )


class EventClusterDiscovery(BaseModel):
    """LLM 聚类结果（经规则修正后）。"""

    primary_cluster_id: str
    clusters: List[EventCluster] = Field(min_length=1)
    anchor_event: Optional[str] = Field(
        default=None,
        description="字典 canonical 锚点事件（展示用）",
    )
    depth_insights: List[str] = Field(
        default_factory=list,
        description="跨聚类的深度洞察建议",
    )
    source: Literal["llm", "rules_fallback"] = "llm"


def _build_cluster_prompt(
    query: str,
    csv_event_names: List[str],
    events_index: dict,
    seed_plan: AnalysisPlan | None,
) -> str:
    pool_lines = [f"- {name}" for name in csv_event_names[:120]]
    if len(csv_event_names) > 120:
        pool_lines.append(f"- … 另有 {len(csv_event_names) - 120} 个取值未列出")

    mapping = build_dict_csv_mapping_hint(events_index, csv_event_names)
    seed_hint = ""
    if seed_plan:
        seed_hint = (
            f"\n## 分析计划草案（可参考，勿被字典模块束缚）\n"
            f"- matched_event: {seed_plan.matched_event}\n"
            f"- csv_event_filter: {seed_plan.csv_event_filter or []}\n"
            f"- analysis_type: {seed_plan.analysis_type}\n"
        )

    return f"""你是座舱埋点数据的「分析场景架构师」。根据用户问题，对数据池中的 event 取值做**语义聚类**，产出可执行的综合分析项。

## 用户问题
{query}

## 数据池 event 列全部取值（过滤与分析只能使用下列值，禁止编造）
{chr(10).join(pool_lines)}

{mapping}
{seed_hint}

## 任务
1. 按**用户意图与业务语义**聚类（如「Carlog 使用链路」「蓝牙连接过程」「导航启停」），**禁止**仅因字典「功能模块」相同就合并。
2. 每个聚类是一个综合分析项：给出 id（snake_case）、name（中文主题）、rationale、csv_events（1~15 个，必须来自上方列表）。
3. 若聚类内存在明显先后转化关系，填写 funnel_order（CSV 取值有序列表，须为 csv_events 子集）。
4. 为每个聚类写 1~3 条 analysis_angles（具体可执行的分析角度，如「对比进入与退出的 UV 流失」）。
5. 选出最贴合用户问题的 primary_cluster_id。
6. anchor_event：可选，字典 canonical 名（若能在映射表中找到）。
7. depth_insights：2~4 条跨聚类或场景级的深挖建议（口语化）。

## 约束
- csv_events 只能来自数据池列表；无关事件不要纳入
- 宁可拆成多个小聚类，也不要把不相关事件硬塞进同一聚类
- 用户只关心单一功能时，可以只输出 1 个聚类（但 csv_events 仍可包含该场景下多个步骤事件）
- 只输出 JSON，格式如下：

{{
  "primary_cluster_id": "carlog_usage",
  "anchor_event": "Carlog_进入",
  "depth_insights": ["…", "…"],
  "clusters": [
    {{
      "id": "carlog_usage",
      "name": "Carlog 使用与留存",
      "rationale": "进入、录制、剪辑等同属一次 Carlog 使用旅程",
      "csv_events": ["carlog_entry", "carlog_exit"],
      "funnel_order": ["carlog_entry", "carlog_record", "carlog_exit"],
      "analysis_angles": ["对比各步骤 UV", "观察退出前录制完成率"]
    }}
  ]
}}"""


def _slug_cluster_id(name: str, index: int) -> str:
    token = re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")
    return token[:40] if token else f"cluster_{index}"


def repair_cluster_discovery(
    data: dict,
    csv_event_names: List[str],
    events_index: dict,
    *,
    query: str = "",
    seed_plan: AnalysisPlan | None = None,
) -> EventClusterDiscovery:
    """校验并修正 LLM 聚类输出；失败字段用规则兜底。"""
    pool = {str(v) for v in csv_event_names}
    raw_clusters = data.get("clusters") or []
    repaired: List[EventCluster] = []
    seen_ids: set[str] = set()

    for idx, item in enumerate(raw_clusters):
        if not isinstance(item, dict):
            continue
        events = sanitize_csv_event_filter(item.get("csv_events"), csv_event_names)
        if not events:
            continue
        cid = str(item.get("id") or "").strip() or _slug_cluster_id(
            str(item.get("name") or f"cluster_{idx}"), idx
        )
        if cid in seen_ids:
            cid = f"{cid}_{idx}"
        seen_ids.add(cid)
        funnel = sanitize_csv_event_filter(item.get("funnel_order"), csv_event_names)
        if funnel and not set(funnel).issubset(set(events)):
            funnel = [e for e in funnel if e in events]
        angles = item.get("analysis_angles") or []
        if not isinstance(angles, list):
            angles = []
        angles = [str(a).strip() for a in angles if str(a).strip()][:5]
        repaired.append(
            EventCluster(
                id=cid,
                name=str(item.get("name") or cid)[:60],
                rationale=str(item.get("rationale") or "语义相关事件组合")[:300],
                csv_events=events,
                funnel_order=funnel or None,
                analysis_angles=angles,
            )
        )

    if not repaired:
        repaired.extend(
            _rules_fallback_clusters(
                query, csv_event_names, events_index, seed_plan
            )
        )

    primary_id = str(data.get("primary_cluster_id") or "").strip()
    if not primary_id or not any(c.id == primary_id for c in repaired):
        primary_id = repaired[0].id

    insights = data.get("depth_insights") or []
    if not isinstance(insights, list):
        insights = []
    insights = [str(i).strip() for i in insights if str(i).strip()][:6]

    anchor = str(data.get("anchor_event") or "").strip() or None
    if seed_plan and seed_plan.matched_event:
        anchor = seed_plan.matched_event
    if not anchor and repaired:
        primary = next(c for c in repaired if c.id == primary_id)
        canonical = _lookup_in_index(events_index, primary.csv_events[0])
        anchor = canonical or primary.csv_events[0]

    return EventClusterDiscovery(
        primary_cluster_id=primary_id,
        clusters=repaired,
        anchor_event=anchor,
        depth_insights=insights,
        source="llm",
    )


def _rules_fallback_clusters(
    query: str,
    csv_event_names: List[str],
    events_index: dict,
    seed_plan: AnalysisPlan | None,
) -> List[EventCluster]:
    """LLM 不可用或输出无效时的规则兜底（不含字典模块全量扩展）。"""
    events: List[str] = []
    if seed_plan and seed_plan.csv_event_filter:
        events = sanitize_csv_event_filter(seed_plan.csv_event_filter, csv_event_names)
    if not events and seed_plan:
        from services.event_mapping import infer_csv_filter_for_canonical

        events = infer_csv_filter_for_canonical(
            seed_plan.matched_event, events_index, csv_event_names
        )
    related = infer_related_csv_events(query, csv_event_names)
    if related and len(related) > len(events):
        events = sorted(related)
    if not events and seed_plan:
        events = sanitize_csv_event_filter(
            [seed_plan.matched_event], csv_event_names
        )
    if not events:
        return []

    name = seed_plan.matched_event if seed_plan else "相关事件"
    if seed_plan and seed_plan.scope_label:
        name = seed_plan.scope_label
    return [
        EventCluster(
            id="fallback_primary",
            name=f"{name} 相关场景",
            rationale="基于问题关键词与计划草案的规则聚类（LLM 聚类未生效）",
            csv_events=events,
            funnel_order=events if len(events) >= 2 else None,
            analysis_angles=["对比各事件触发量与 UV", "观察时间趋势差异"],
        )
    ]


def discover_event_clusters(
    query: str,
    csv_event_names: List[str],
    events_index: dict,
    *,
    seed_plan: AnalysisPlan | None = None,
) -> EventClusterDiscovery:
    """调用 LLM 做事件聚类；失败时规则兜底。"""
    if not csv_event_names:
        raise ValueError("数据池无 event 取值，无法聚类")

    try:
        client = _create_client()
    except MissingApiKeyError:
        clusters = _rules_fallback_clusters(
            query, csv_event_names, events_index, seed_plan
        )
        if not clusters:
            raise MissingApiKeyError("DEEPSEEK_API_KEY 未配置")
        return EventClusterDiscovery(
            primary_cluster_id=clusters[0].id,
            clusters=clusters,
            anchor_event=seed_plan.matched_event if seed_plan else None,
            depth_insights=[],
            source="rules_fallback",
        )

    prompt = _build_cluster_prompt(query, csv_event_names, events_index, seed_plan)

    try:
        response = client.chat.completions.create(
            model=get_deepseek_model(),
            messages=[
                {
                    "role": "system",
                    "content": "你只输出 JSON，擅长座舱埋点场景聚类与可执行分析设计。",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except APITimeoutError as exc:
        raise LLMApiError(
            f"事件聚类请求超时（{REQUEST_TIMEOUT_SECONDS:.0f} 秒）", cause=exc
        ) from exc
    except APIConnectionError as exc:
        raise LLMApiError("事件聚类 API 连接失败", cause=exc) from exc
    except APIStatusError as exc:
        raise LLMApiError(
            f"事件聚类 API 错误: {exc.status_code} {exc.message}", cause=exc
        ) from exc
    except Exception as exc:
        raise LLMApiError(f"事件聚类调用异常: {exc}", cause=exc) from exc

    if not response.choices:
        raise LLMApiError("事件聚类 API 返回为空")

    raw = response.choices[0].message.content or ""
    try:
        data = _parse_llm_json(raw)
    except Exception:
        data = json.loads(raw) if raw.strip().startswith("{") else {}

    try:
        return repair_cluster_discovery(
            data, csv_event_names, events_index, query=query, seed_plan=seed_plan
        )
    except ValidationError as exc:
        repaired = _rules_fallback_clusters(
            query, csv_event_names, events_index, seed_plan
        )
        if not repaired:
            raise LLMApiError(f"事件聚类结果无效: {exc}") from exc
        return EventClusterDiscovery(
            primary_cluster_id=repaired[0].id,
            clusters=repaired,
            anchor_event=seed_plan.matched_event if seed_plan else None,
            depth_insights=[],
            source="rules_fallback",
        )


def get_primary_cluster(
    discovery: EventClusterDiscovery,
) -> EventCluster:
    for cluster in discovery.clusters:
        if cluster.id == discovery.primary_cluster_id:
            return cluster
    return discovery.clusters[0]


def scope_from_cluster(cluster: EventCluster) -> Set[str]:
    return set(cluster.csv_events)


def comparison_steps_from_cluster(
    cluster: EventCluster,
    events_index: dict,
) -> List[str]:
    """漏斗/对比用的步骤列表（优先 CSV 取值，便于聚合）。"""
    if cluster.funnel_order:
        return list(cluster.funnel_order)
    return list(cluster.csv_events)


def apply_cluster_to_plan(
    plan: AnalysisPlan,
    discovery: EventClusterDiscovery,
    cluster: EventCluster,
) -> AnalysisPlan:
    """将主聚类写入分析计划。"""
    steps = comparison_steps_from_cluster(cluster, events_index)
    updates: dict = {
        "csv_event_filter": sorted(cluster.csv_events),
        "scope_label": cluster.name,
        "comparison_events": steps if len(steps) >= 2 else None,
    }
    if discovery.anchor_event:
        updates["matched_event"] = discovery.anchor_event
    return plan.model_copy(update=updates)


def discovery_scope_label(discovery: EventClusterDiscovery) -> str:
    cluster = get_primary_cluster(discovery)
    return cluster.name


def build_discovery_from_scope(
    query: str,
    scope: Set[str],
    events_index: dict,
    csv_event_names: List[str],
    seed_plan: AnalysisPlan | None = None,
) -> EventClusterDiscovery:
    """聚类 LLM 不可用但已有事件范围时，构造最小 discovery。"""
    data = {
        "primary_cluster_id": "fallback_primary",
        "clusters": [
            {
                "id": "fallback_primary",
                "name": (seed_plan.scope_label if seed_plan and seed_plan.scope_label else None)
                or (seed_plan.matched_event if seed_plan else "综合分析"),
                "rationale": "基于分析计划与关键词规则归并的事件组",
                "csv_events": sorted(scope),
            }
        ],
        "depth_insights": [],
    }
    result = repair_cluster_discovery(
        data, csv_event_names, events_index, query=query, seed_plan=seed_plan
    )
    return result.model_copy(update={"source": "rules_fallback"})
