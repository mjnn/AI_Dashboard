"""LLM 分析规划服务（DeepSeek 兼容调用）。"""

from __future__ import annotations

import json
import re
from typing import Any, List, Set

from openai import APIConnectionError, APITimeoutError, APIStatusError, OpenAI
from pydantic import ValidationError

from config import get_deepseek_api_key
from schemas.analysis import AnalysisPlan
from services.analysis_registry import (
    build_analysis_catalog_prompt,
    build_chart_catalog_prompt,
    normalize_plan_for_analysis,
    repair_funnel_analysis_plan,
    repair_usage_retention_plan,
)
from services.event_mapping import build_dict_csv_mapping_hint, repair_plan_event_adaptation
from services.field_resolver import resolve_event

from services.llm_settings import get_deepseek_model
from services.locale import locale_instruction

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
REQUEST_TIMEOUT_SECONDS = 10.0

_JSON_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)


class MissingApiKeyError(Exception):
    """DeepSeek API Key 未配置。"""


class LLMApiError(Exception):
    """调用 DeepSeek API 失败。"""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class AnalysisPlanError(Exception):
    """AnalysisPlan 解析或校验失败。"""

    def __init__(self, message: str, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output


def build_events_whitelist(modules: List[dict]) -> str:
    """将模块分组事件格式化为 LLM system prompt 可用的白名单文本。"""
    lines = ["## 可用事件列表"]
    for module in modules:
        name = module.get("name", "")
        events = module.get("events", [])
        if not name:
            continue
        lines.append(f"### {name}")
        for event in events:
            lines.append(f"- {event}")
    return "\n".join(lines)


def parse_event_names_from_whitelist(events_whitelist: str) -> Set[str]:
    """从白名单文本中提取字典 canonical 事件名集合。"""
    names: Set[str] = set()
    for line in events_whitelist.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            names.add(stripped[2:].strip())
        elif stripped.startswith("* "):
            names.add(stripped[2:].strip())
    return names


def build_allowed_event_names(events_index: dict) -> Set[str]:
    """canonical 名 + 全部别名（含 CSV label），供 LLM 输出校验。"""
    allowed: Set[str] = set()
    for name, definition in events_index.get("events", {}).items():
        allowed.add(name)
        for alias in definition.get("aliases", []):
            allowed.add(str(alias))
    return allowed


def _build_csv_events_hint(
    csv_event_names: List[str] | None,
    csv_columns: List[str] | None = None,
    events_index: dict | None = None,
) -> str:
    if not csv_event_names and not csv_columns:
        return ""
    lines: List[str] = []
    if events_index and csv_event_names:
        lines.append(build_dict_csv_mapping_hint(events_index, csv_event_names).rstrip())
    elif csv_event_names:
        lines.append("## 当前数据池中的 event 列取值（分析过滤以这些为准）")
        for name in csv_event_names[:40]:
            lines.append(f"- {name}")
    if csv_columns:
        lines.append("## 当前数据池 CSV 列名")
        for col in csv_columns[:30]:
            lines.append(f"- {col}")
    lines.append(
        "## 事件名适配规则（重要）\n"
        "字典中的 matched_event（如 Carlog_进入）与 CSV event 列（如 carlog_entry）格式常不一致。\n"
        "你必须同时输出：\n"
        "- matched_event：字典 canonical 名（展示/口径用）\n"
        "- csv_event_filter：本次分析在 CSV 中实际过滤的 event 取值列表（必填，可多值）\n"
        "- event_mapping_note：一句话说明为何这样映射（可选）\n"
        "模块级问题（如「分析 carlog」）应把语义相关的 CSV event 写入 csv_event_filter（由后续聚类进一步修正）。\n"
        "用户关注某一功能/场景时，纳入该场景下多个步骤事件，勿仅选单点；**不要**因字典模块相同就合并无关事件。\n"
        "单事件问题只写对应的一个或多个 CSV 取值。csv_event_filter 只能来自上方数据池列表，不要编造。\n"
        "dimension / metrics.field 必须来自 CSV 列名或字典属性，不要编造字段。"
    )
    return "\n".join(lines) + "\n"


def _build_system_prompt(
    events_whitelist: str,
    csv_event_names: List[str] | None = None,
    csv_columns: List[str] | None = None,
    events_index: dict | None = None,
    *,
    locale: str | None = None,
) -> str:
    catalog = build_analysis_catalog_prompt()
    chart_catalog = build_chart_catalog_prompt()
    csv_hint = _build_csv_events_hint(csv_event_names, csv_columns, events_index)
    body = f"""你是一位座舱埋点数据分析师。你的任务是根据用户的问题，生成一个完整的分析计划。

{events_whitelist}

{csv_hint}

{catalog}

{chart_catalog}

## 可用指标类型
- count: 计数（触发次数/PV）
- nunique: 按车去重（UV），需指定去重字段（如 vin_code）
- formula: 复合指标，表达式如 "pv / uv_vin"（渗透率），需 formula_components

## 输出要求
请输出一个 JSON 格式的分析计划，字段包括：
- analysis_type: 必填，从上述分析类型枚举中选择
- comparison_events: 漏斗/多事件对比时必填，有序事件名列表
- top_n: top_n_ranking 时的 N 值（默认 10）
- cohort_retention_days: 队列留存观测天（默认 [1,3,7,14,30]）
- period_unit: period_pattern 时 hour 或 weekday
- intent_confidence: high/medium/low（分析意图是否明确；笼统问题如「分析一下」设为 low）
- exploratory_mode: true/false（用户明确要求「全面/整体/综合」分析时为 true）
- matched_event: 你认为用户想分析哪个事件（字典名，必须从可用事件列表选择；多事件综合时选模块代表事件）
- csv_event_filter: 数据池 CSV event 列实际过滤取值（字符串数组，必填；相关事件应全部列入）
- event_mapping_note: 字典名与 CSV 取值的映射说明（可选）
- match_confidence: high/medium/low
- matched_module: 该事件所属模块
- metrics: 需要计算的指标列表
- statistical_caliber: 统计口径说明（去重方式、聚合粒度、口径描述）
- visualization: 图表类型、布局和选型理由（chart_type 必须属于该 analysis_type 的可选图表）
- dimension: 主分析维度（按 analysis_type 对应的 dimension 填写）
- sub_dimension: 次级维度（cross_dimension / heatmap_time / event_comparison 等时必填）
- filters: 过滤条件
- time_range: 时间范围

## 约束
- analysis_type 决定后端聚合逻辑，必须准确选择
- visualization.chart_type 必须属于当前 analysis_type 的「可选图表」，优先使用「默认图表」
- visualization.layout 只能是 single、dual、grid 之一
- matched_event 必须在上述可用事件列表中，不要编造
- csv_event_filter 必须来自数据池 event 列取值，格式不一致时由你完成适配
- metrics[].type 只能是 count、nunique、formula 之一
- metrics[].formula_components 必须是字符串数组（如 ["pv","uv_vin"]），禁止用 numerator/denominator 对象
- time_range.type 只能是 last_n_days 或 date_range
- intent_confidence=low 或 exploratory_mode=true 时，后端将自动执行当前 CSV 可支持的全量探索分析
- 用户问题具体、分析目标清晰时 intent_confidence=high；仅说「分析一下」「看看情况」等设为 low
- usage_retention / usage_distribution: dimension 固定为「使用次数分组」
- summary_kpi / repeat_rate / stickiness: dimension 固定为 "_summary"
- funnel: chart_type 优先 funnel_chart；event_comparison 时间对比优先 multi_line
- 只输出 JSON 对象，不要任何额外文字

## 示例1：时间趋势
用户问题："蓝牙连接的近30天每日使用趋势"
输出:
{{
  "analysis_type": "time_series",
  "matched_event": "蓝牙连接成功",
  "matched_module": "蓝牙",
  "match_confidence": "high",
  "metrics": [
    {{"id": "pv", "name": "触发次数", "type": "count"}},
    {{"id": "uv_vin", "name": "按车去重", "type": "nunique", "field": "vin_code"}}
  ],
  "statistical_caliber": {{
    "dedup_method": "按VIN去重计UV",
    "time_granularity": "daily",
    "description": "统计每日独立VIN触发蓝牙连接成功的总次数，按日聚合。UV基于vin_code去重计算。"
  }},
  "visualization": {{
    "chart_type": "line",
    "layout": "single",
    "reasoning": "用户想了解趋势变化，折线图最适合展示时间序列趋势"
  }},
  "dimension": "date",
  "filters": {{}},
  "time_range": {{"type": "last_n_days", "value": 30}}
}}

## 示例2：留存分桶
用户问题："Carlog使用1次和2次的车辆数"
输出:
{{
  "analysis_type": "usage_retention",
  "matched_event": "Carlog_进入",
  "csv_event_filter": ["carlog_entry"],
  "event_mapping_note": "字典 Carlog_进入 对应 CSV carlog_entry",
  "matched_module": "Carlog",
  "match_confidence": "high",
  "metrics": [
    {{"id": "vehicle_count", "name": "车辆数", "type": "count"}}
  ],
  "statistical_caliber": {{
    "dedup_method": "按VIN去重",
    "time_granularity": "daily",
    "description": "统计时间范围内各VIN使用Carlog的次数，分桶为使用1次和使用2次，统计各桶车辆数"
  }},
  "visualization": {{
    "chart_type": "bar",
    "layout": "single",
    "reasoning": "留存分桶适合柱状图对比各桶车辆数"
  }},
  "dimension": "使用次数分组",
  "filters": {{}},
  "time_range": {{"type": "last_n_days", "value": 30}}
}}"""
    return body + locale_instruction(locale)


def _parse_llm_json(content: str) -> dict:
    """解析 LLM 返回内容为 JSON 对象。"""
    text = content.strip()
    if not text:
        raise AnalysisPlanError("LLM 返回为空", raw_output=content)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    block_match = _JSON_BLOCK_PATTERN.search(text)
    if block_match:
        try:
            return json.loads(block_match.group(1))
        except json.JSONDecodeError as exc:
            raise AnalysisPlanError(
                f"JSON 代码块解析失败: {exc}", raw_output=content
            ) from exc

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AnalysisPlanError(
                f"JSON 片段解析失败: {exc}", raw_output=content
            ) from exc

    raise AnalysisPlanError("无法解析 LLM 返回的 JSON", raw_output=content)


def _normalize_formula_component_id(raw: str) -> str | None:
    """将 LLM 表达式键名规范为 formula_components 可用的指标 id。"""
    text = raw.strip()
    if not text:
        return None
    unique_match = re.match(r"n?unique\s*\(\s*(\w+)\s*\)", text, re.I)
    if unique_match:
        field = unique_match.group(1).lower()
        if field in ("vin_code", "vin"):
            return "uv_vin"
        return f"uv_{field}"
    if re.fullmatch(r"count\s*\(\s*\*?\s*\)", text, re.I):
        return "pv"
    if re.fullmatch(r"[\w]+", text):
        return text
    slug = re.sub(r"[^\w]+", "_", text).strip("_")
    return slug or None


def _extract_formula_ids_from_expression(formula: str) -> list[str] | None:
    if not formula or not isinstance(formula, str):
        return None
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", formula)
    keywords = {"and", "or", "not", "if", "else", "true", "false"}
    ids = [token for token in tokens if token.lower() not in keywords]
    return ids or None


def _coerce_formula_components(value: Any) -> list[str] | None:
    """将 LLM 常见的 dict 形态 formula_components 规范为指标 id 列表。"""
    if value is None:
        return None
    if isinstance(value, list):
        parts = [
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        ]
        return parts or None
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("numerator", "denominator", "components", "deps", "depends_on"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, list):
                parts.extend(
                    str(x).strip() for x in item if x is not None and str(x).strip()
                )
        if not parts:
            for key, item in value.items():
                if isinstance(item, dict):
                    comp_id = item.get("id") or item.get("metric_id") or item.get("name")
                    if isinstance(comp_id, str) and comp_id.strip():
                        parts.append(comp_id.strip())
                        continue
                    field = item.get("field")
                    if isinstance(field, str) and field.strip():
                        normalized = _normalize_formula_component_id(str(key))
                        parts.append(normalized or f"uv_{field.strip()}")
                        continue
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                elif isinstance(item, list):
                    parts.extend(
                        str(x).strip() for x in item if x is not None and str(x).strip()
                    )
                normalized_key = _normalize_formula_component_id(str(key))
                if normalized_key:
                    parts.append(normalized_key)
        deduped: list[str] = []
        seen: set[str] = set()
        for part in parts:
            if part not in seen:
                seen.add(part)
                deduped.append(part)
        return deduped or None
    return None


def repair_plan_llm_payload(
    data: dict,
    *,
    query: str = "",
    csv_event_names: List[str] | None = None,
    events_index: dict | None = None,
) -> dict:
    """修正 LLM 输出中易触发 Pydantic 校验失败的字段。"""
    payload = dict(data)
    if not payload.get("match_confidence"):
        payload["match_confidence"] = "medium"

    metrics = payload.get("metrics")
    if isinstance(metrics, list):
        repaired_metrics: list[Any] = []
        for item in metrics:
            if not isinstance(item, dict):
                repaired_metrics.append(item)
                continue
            metric = dict(item)
            if "formula_components" in metric:
                metric["formula_components"] = _coerce_formula_components(
                    metric.get("formula_components")
                )
            repaired_metrics.append(metric)
        payload["metrics"] = repaired_metrics

    payload = repair_usage_retention_plan(
        payload,
        query,
        csv_event_names=csv_event_names,
        events_index=events_index,
    )
    payload = repair_funnel_analysis_plan(
        payload,
        query,
        csv_event_names=csv_event_names,
        events_index=events_index,
    )
    return payload


def _canonicalize_plan_events(
    plan: AnalysisPlan,
    events_index: dict,
    *,
    csv_event_names: List[str] | None = None,
    query: str = "",
) -> AnalysisPlan:
    """将 matched_event / comparison_events 解析为 canonical 名称。"""
    updates: dict = {}

    resolved = resolve_event(
        plan.matched_event,
        events_index,
        csv_event_names=csv_event_names,
        query=query,
    )
    if resolved.event_name != plan.matched_event:
        updates["matched_event"] = resolved.event_name
    module = resolved.event_def.get("module")
    if module and not plan.matched_module:
        updates["matched_module"] = module

    if plan.comparison_events:
        canonical_events: list[str] = []
        for event_name in plan.comparison_events:
            canonical_events.append(
                resolve_event(
                    event_name,
                    events_index,
                    csv_event_names=csv_event_names,
                    query=query,
                ).event_name
            )
        if canonical_events != plan.comparison_events:
            updates["comparison_events"] = canonical_events

    if updates:
        return plan.model_copy(update=updates)
    return plan


def _validate_plan(
    data: dict,
    raw_output: str,
    events_index: dict | None = None,
    *,
    csv_event_names: List[str] | None = None,
    query: str = "",
) -> AnalysisPlan:
    """用 Pydantic 校验；事件名通过 CSV 上下文解析，不因白名单不匹配而失败。"""
    try:
        plan = AnalysisPlan.model_validate(data)
    except ValidationError as exc:
        raise AnalysisPlanError(
            f"AnalysisPlan 校验失败: {exc}", raw_output=raw_output
        ) from exc

    if events_index:
        plan = _canonicalize_plan_events(
            plan,
            events_index,
            csv_event_names=csv_event_names,
            query=query,
        )
        resolve_event(
            plan.matched_event,
            events_index,
            csv_event_names=csv_event_names,
            query=query,
        )

    return normalize_plan_for_analysis(plan, query=query)


def _create_client() -> OpenAI:
    api_key = get_deepseek_api_key()
    if not api_key:
        raise MissingApiKeyError(
            "DEEPSEEK_API_KEY 未配置，请在 backend/.env 中设置 DEEPSEEK_API_KEY"
        )
    return OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def generate_plan(
    query: str,
    events_whitelist: str,
    *,
    events_index: dict | None = None,
    csv_event_names: List[str] | None = None,
    csv_columns: List[str] | None = None,
    locale: str | None = None,
) -> AnalysisPlan:
    """调用 DeepSeek 生成并校验分析计划。"""
    client = _create_client()
    system_prompt = _build_system_prompt(
        events_whitelist,
        csv_event_names,
        csv_columns,
        events_index,
        locale=locale,
    )

    try:
        response = client.chat.completions.create(
            model=get_deepseek_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    except APITimeoutError as exc:
        raise LLMApiError(
            f"DeepSeek API 请求超时（{REQUEST_TIMEOUT_SECONDS:.0f} 秒）", cause=exc
        ) from exc
    except APIConnectionError as exc:
        raise LLMApiError("DeepSeek API 连接失败", cause=exc) from exc
    except APIStatusError as exc:
        raise LLMApiError(
            f"DeepSeek API 返回错误: {exc.status_code} {exc.message}", cause=exc
        ) from exc
    except Exception as exc:
        raise LLMApiError(f"DeepSeek API 调用异常: {exc}", cause=exc) from exc

    if not response.choices:
        raise LLMApiError("DeepSeek API 返回为空")

    raw_output = response.choices[0].message.content or ""
    data = _parse_llm_json(raw_output)

    if events_index and csv_event_names:
        data = repair_plan_event_adaptation(data, events_index, csv_event_names, query)

    data = repair_plan_llm_payload(
        data,
        query=query,
        csv_event_names=csv_event_names,
        events_index=events_index,
    )

    return _validate_plan(
        data,
        raw_output,
        events_index,
        csv_event_names=csv_event_names,
        query=query,
    )
