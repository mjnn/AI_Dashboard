"""基于数据画像的 LLM 分析推荐。"""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from config import data_pool_cache_key, get_deepseek_api_key
from schemas.analysis import AnalysisRecommendation, RecommendationsResponse
from services.analysis_registry import ANALYSIS_SPEC_BY_ID, build_analysis_catalog_prompt
from services.data_profiler import build_data_profile
from services.llm_planner import (
    AnalysisPlanError,
    DEEPSEEK_BASE_URL,
    LLMApiError,
    MissingApiKeyError,
    REQUEST_TIMEOUT_SECONDS,
    _create_client,
    _parse_llm_json,
)
from services.llm_settings import get_deepseek_model
from services.locale import locale_instruction, normalize_locale

RecommendationMode = Literal["auto", "precise", "exploratory"]

_cache: dict[str, RecommendationsResponse] = {}


class _RecommendationItem(BaseModel):
    title: str = Field(min_length=1, max_length=40)
    query: str = Field(min_length=1, max_length=200)
    analysis_mode: RecommendationMode = "auto"
    reason: str = Field(min_length=1, max_length=200)
    analysis_type: Optional[str] = None


class _RecommendationPayload(BaseModel):
    recommendations: List[_RecommendationItem] = Field(min_length=3, max_length=8)


def _format_profile_for_prompt(profile: dict[str, Any]) -> str:
    lines = [
        f"- 列: {', '.join(profile.get('columns', []))}",
        f"- 总行数: {profile.get('total_rows', 0)}",
    ]
    if "date_range" in profile:
        dr = profile["date_range"]
        lines.append(f"- 时间跨度: {dr['start']} ~ {dr['end']}（{dr['span_days']} 天）")
    if "daily_volume" in profile:
        dv = profile["daily_volume"]
        lines.append(
            f"- 日均触发: {dv['avg']} 次，峰值日 {dv['max_day']}（{dv['max_count']} 次）"
        )
    if "events" in profile:
        event_text = "、".join(
            f"{e['name']}({e['count']}次)" for e in profile["events"][:5]
        )
        lines.append(f"- 事件: {event_text}")
    if "unique_vins" in profile:
        lines.append(f"- 按车去重(VIN): {profile['unique_vins']}")
    if "usage_per_vin" in profile:
        up = profile["usage_per_vin"]
        lines.append(
            f"- 每车使用次数: 均值 {up['avg']}，中位 {up['median']}，最大 {up['max']}"
        )
    if profile.get("extra_dimensions"):
        lines.append(f"- 可用维度列: {', '.join(profile['extra_dimensions'])}")
    feasible = profile.get("feasible_analysis_types", [])
    if feasible:
        type_labels = []
        for type_id in feasible[:12]:
            spec = ANALYSIS_SPEC_BY_ID.get(type_id)
            label = spec["name"] if spec else type_id
            type_labels.append(f"{type_id}({label})")
        lines.append(f"- 当前数据可执行分析: {', '.join(type_labels)}")
    return "\n".join(lines)


def _build_recommendation_prompt(profile: dict[str, Any]) -> str:
    catalog = build_analysis_catalog_prompt()
    profile_text = _format_profile_for_prompt(profile)
    primary_event = ""
    if profile.get("events"):
        primary_event = profile["events"][0]["name"]

    return f"""你是一位座舱埋点数据分析顾问。根据下方**真实 CSV 数据画像**，为用户生成 4~6 条可直接提交的分析问题推荐。

## 当前数据画像
{profile_text}

{catalog}

## 输出要求
输出 JSON 对象，字段 recommendations 为数组，每项包含：
- title: 简短标签（8 字以内，如「日趋势」「留存分桶」）
- query: 完整自然语言分析问题（用户可直接点击执行，需包含具体事件名）
- analysis_mode: auto / precise / exploratory 之一
  - auto: 常规单一分析
  - precise: 明确单一指标
  - exploratory: 用户想全面了解情况（如「整体分析」「综合看看」）
- reason: 一句话说明为何推荐（结合数据特征，如车辆数、时间跨度、使用量分布）
- analysis_type: 对应的 analysis_type 枚举值（可选）

## 约束
- 推荐必须基于上述真实数据，不要编造不存在的事件或维度
- 主事件优先使用: {primary_event or "数据中的事件名"}
- 至少 1 条探索性推荐（analysis_mode=exploratory），当数据适合全面诊断时
- 至少 1 条趋势类（time_series 或 growth_rate）
- 至少 1 条用户行为类（usage_retention / new_vs_returning / stickiness 等）
- query 要具体可执行，避免空泛的「分析一下数据」
- 时间范围优先用 last_n_days，天数不超过数据 span_days
- 只输出 JSON，不要额外文字

## 示例输出结构
{{
  "recommendations": [
    {{
      "title": "日趋势",
      "query": "Carlog进入最近21天每日触发趋势",
      "analysis_mode": "auto",
      "reason": "21 天数据适合观察日活波动，峰值日可进一步对比",
      "analysis_type": "time_series"
    }}
  ]
}}"""


def _validate_recommendations(data: dict, raw_output: str) -> List[AnalysisRecommendation]:
    try:
        payload = _RecommendationPayload.model_validate(data)
    except ValidationError as exc:
        raise AnalysisPlanError(
            f"推荐结果校验失败: {exc}", raw_output=raw_output
        ) from exc

    return [
        AnalysisRecommendation(
            title=item.title,
            query=item.query,
            analysis_mode=item.analysis_mode,
            reason=item.reason,
            analysis_type=item.analysis_type,
        )
        for item in payload.recommendations
    ]


def generate_recommendations(locale: str | None = None) -> RecommendationsResponse:
    """基于数据池画像调用 LLM 生成分析推荐（带缓存）。"""
    lang = normalize_locale(locale)
    key = f"{data_pool_cache_key()}:{lang}"
    if key in _cache:
        return _cache[key]

    profile = build_data_profile()

    if not get_deepseek_api_key():
        return _fallback_recommendations(profile)

    client = _create_client()
    system_prompt = _build_recommendation_prompt(profile) + locale_instruction(lang)

    try:
        response = client.chat.completions.create(
            model=get_deepseek_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请根据数据画像生成分析推荐。"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        if isinstance(exc, (MissingApiKeyError, LLMApiError)):
            raise
        raise LLMApiError(f"推荐生成失败: {exc}", cause=exc) from exc

    if not response.choices:
        raise LLMApiError("DeepSeek API 返回为空")

    raw_output = response.choices[0].message.content or ""
    data = _parse_llm_json(raw_output)
    items = _validate_recommendations(data, raw_output)

    result = RecommendationsResponse(
        data_summary=profile,
        recommendations=items,
        source="llm",
    )
    _cache[key] = result
    return result


def clear_recommendations_cache() -> None:
    """数据池变更后清空推荐缓存。"""
    _cache.clear()


def _fallback_recommendations(profile: dict[str, Any]) -> RecommendationsResponse:
    """无 API Key 时基于规则生成兜底推荐。"""
    event_name = "数据事件"
    span_days = 30
    if profile.get("events"):
        event_name = profile["events"][0]["name"]
    if profile.get("date_range"):
        span_days = min(profile["date_range"]["span_days"], 30)

    items = [
        AnalysisRecommendation(
            title="日趋势",
            query=f"{event_name}最近{span_days}天每日使用趋势",
            analysis_mode="auto",
            reason="观察每日触发量变化，发现峰值与低谷",
            analysis_type="time_series",
        ),
        AnalysisRecommendation(
            title="留存分桶",
            query=f"{event_name}使用1次和2次的车辆数分布",
            analysis_mode="auto",
            reason="了解用户粘性分层，识别一次性与回访用户",
            analysis_type="usage_retention",
        ),
        AnalysisRecommendation(
            title="核心指标",
            query=f"{event_name}核心 KPI 汇总",
            analysis_mode="auto",
            reason="快速掌握 PV、UV 与渗透率等关键指标",
            analysis_type="summary_kpi",
        ),
        AnalysisRecommendation(
            title="全面探索",
            query=f"全面分析一下{event_name}",
            analysis_mode="exploratory",
            reason="对当前数据运行全部可行分析，获得完整画像",
            analysis_type=None,
        ),
    ]
    return RecommendationsResponse(
        data_summary=profile,
        recommendations=items,
        source="fallback",
    )
