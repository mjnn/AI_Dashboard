"""用户可见的事件名称（按界面语言，禁止直接展示 CSV 英文代号）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, List, Optional, Set

from services.analysis_registry import EVENT_NAME_DIMENSION, FUNNEL_STEP_DIMENSION
from services.field_resolver import _lookup_in_index, normalize_token
from services.locale import AppLocale, locale_instruction, normalize_locale

logger = logging.getLogger(__name__)

_CSV_ID_PATTERN = re.compile(r"^hu[_a-z0-9]+$", re.IGNORECASE)
_STEP_PREFIX = re.compile(r"^(Step\s*\d+\s*:)\s*(.+)$", re.IGNORECASE)
_CJK = re.compile(r"[\u4e00-\u9fff]")
_PAREN_BLOCK = re.compile(r"[（(][^）)]*[）)]")

_MODULE_EN = {
    "导航": "Navigation",
    "Carlog": "Carlog",
    "音乐": "Music",
    "空调": "Climate",
    "行车": "Driving",
}

_WORD_EN: dict[str, str] = {
    "导航": "Navigation",
    "进入": "Enter",
    "退出": "Exit",
    "结束": "End",
    "继续": "Continue",
    "发起": "Start",
    "点击": "Tap",
    "弹窗": "Dialog",
    "关闭": "Close",
    "弹出": "Show",
    "沉浸态": "Immersive",
    "非沉浸态": "Non-immersive",
    "用户": "User",
    "状态": "Status",
    "模式": "Mode",
    "熟路": "Familiar route",
    "算路": "Route planning",
    "录制": "Record",
}

# locale|canonical -> 简短展示别名
_display_alias_cache: dict[str, str] = {}


def clear_display_alias_cache() -> None:
    _display_alias_cache.clear()


def _cache_key(canonical: str, locale: AppLocale) -> str:
    return f"{locale}|{canonical}"


def register_display_aliases(aliases: dict[str, str], *, locale: str | None) -> None:
    locale_code = normalize_locale(locale)
    for canonical, alias in aliases.items():
        short = str(alias or "").strip()
        if canonical and short:
            _display_alias_cache[_cache_key(canonical, locale_code)] = short


def _needs_short_alias(name: str) -> bool:
    text = name.strip()
    if not text:
        return False
    if _PAREN_BLOCK.search(text):
        return True
    if len(text) > 14:
        return True
    return False


def heuristic_short_alias(name: str) -> str:
    """规则缩短字典里的冗长事件名（去括号说明、截断枚举从句）。"""
    text = name.strip()
    if not text:
        return text
    text = _PAREN_BLOCK.sub("", text).strip()
    text = re.sub(r"[（(].*", "", text).strip()
    for sep in ("，包括", "，含", "：", "——", "—"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    for prefix in ("用户使用", "用户操作", "用户"):
        if text.startswith(prefix) and len(text) > len(prefix) + 1:
            text = text[len(prefix) :].strip()
            break
    if len(text) > 14:
        text = text[:14].rstrip("，、 ")
    return text or name


def _csv_to_canonical_index(events_index: dict) -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, defn in events_index.get("events", {}).items():
        index[normalize_token(canonical)] = canonical
        for alias in defn.get("aliases", []):
            index[normalize_token(str(alias))] = canonical
    return index


def resolve_canonical_event_ref(
    event_ref: str,
    events_index: dict | None,
) -> tuple[str, str, bool]:
    """返回 (canonical, module, found_in_dict)。"""
    raw = str(event_ref or "").strip()
    if not raw or not events_index:
        return raw, "", False
    index = _csv_to_canonical_index(events_index)
    found = index.get(normalize_token(raw)) or _lookup_in_index(events_index, raw)
    if found:
        module = events_index.get("events", {}).get(found, {}).get("module", "")
        return found, module, True
    return raw, "", False


def collect_scope_event_refs(
    *,
    matched_event: str,
    comparison_events: List[str] | None = None,
    csv_event_filter: List[str] | None = None,
    events_index: dict | None,
) -> List[str]:
    refs: Set[str] = set()
    if matched_event:
        refs.add(matched_event)
    if comparison_events:
        refs.update(comparison_events)
    if csv_event_filter:
        refs.update(csv_event_filter)
    if events_index:
        canonicals: Set[str] = set()
        for ref in refs:
            canonical, _, _ = resolve_canonical_event_ref(ref, events_index)
            canonicals.add(canonical)
        return sorted(canonicals)
    return sorted(refs)


def _llm_short_aliases(
    items: List[dict[str, str]],
    *,
    locale: str | None,
) -> dict[str, str]:
    if not items:
        return {}
    from openai import OpenAI

    from config import get_deepseek_api_key
    from services.llm_planner import (
        DEEPSEEK_BASE_URL,
        LLMApiError,
        MissingApiKeyError,
        _parse_llm_json,
    )
    from services.llm_settings import get_deepseek_model

    api_key = get_deepseek_api_key()
    if not api_key:
        raise MissingApiKeyError("DEEPSEEK_API_KEY 未配置")

    locale_code = normalize_locale(locale)
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    system = f"""你是座舱埋点事件的「命名编辑」。请为每个事件生成**简短、易懂**的展示别名。
{locale_instruction(locale_code)}

## 要求
- 别名 2~10 个字（英文 2~5 个词），面向运营/产品，一眼能懂
- **禁止**照搬字典全名，**禁止**保留括号内长说明
- 好：「发起导航」「结束导航」「Carlog 进入」
- 坏：「用户发起导航（包括算路进入导航、poi…）」
- 每个 canonical 必须有唯一 alias

## 输出 JSON
{{"aliases": {{"字典canonical全名": "短别名", "...": "..."}}}}
只输出 JSON。"""
    user = f"## 待命名事件\n{payload}"
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
            timeout=18.0,
        )
        response = client.chat.completions.create(
            model=get_deepseek_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = response.choices[0].message.content or ""
        data = _parse_llm_json(raw)
    except MissingApiKeyError:
        raise
    except Exception as exc:
        logger.warning("事件短别名 LLM 失败，使用规则兜底: %s", exc)
        return {}
    raw_aliases = data.get("aliases") if isinstance(data, dict) else {}
    if not isinstance(raw_aliases, dict):
        return {}
    return {
        str(k): str(v).strip()
        for k, v in raw_aliases.items()
        if k and v and str(v).strip()
    }


def warm_display_aliases(
    event_refs: Iterable[str],
    events_index: dict,
    *,
    locale: str | None = None,
    use_llm: bool = True,
) -> None:
    """为分析范围内的冗长事件名预生成展示别名。"""
    locale_code = normalize_locale(locale)
    llm_candidates: List[dict[str, str]] = []
    pending: dict[str, str] = {}

    for ref in event_refs:
        canonical, module, found = resolve_canonical_event_ref(ref, events_index)
        if not found or not _needs_short_alias(canonical):
            continue
        key = _cache_key(canonical, locale_code)
        if key in _display_alias_cache:
            continue
        short = heuristic_short_alias(canonical)
        pending[canonical] = short
        event_def = events_index.get("events", {}).get(canonical, {})
        llm_candidates.append(
            {
                "canonical": canonical,
                "module": module,
                "condition": (event_def.get("condition") or "")[:120],
                "heuristic_hint": short,
            }
        )

    if use_llm and llm_candidates:
        llm_aliases = _llm_short_aliases(llm_candidates, locale=locale_code)
        for canonical, alias in llm_aliases.items():
            if canonical in pending and alias:
                pending[canonical] = alias[:20].strip()

    for canonical, alias in pending.items():
        _display_alias_cache[_cache_key(canonical, locale_code)] = alias


def _looks_like_csv_technical_id(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if _CJK.search(text):
        return False
    return bool(_CSV_ID_PATTERN.match(text)) or (
        text.isascii() and ("_" in text or text.lower().startswith("hu"))
    )


def _translate_zh_name(name: str, locale: AppLocale) -> str:
    if locale == "zh" or not _CJK.search(name):
        return name
    table = _WORD_EN
    result = name
    for zh, translated in sorted(table.items(), key=lambda item: -len(item[0])):
        result = result.replace(zh, translated)
    result = _CJK.sub(" ", result)
    result = re.sub(r"\s+", " ", result).strip(" ·|-")
    return result or name


def _humanize_csv_label(label: str) -> str:
    text = re.sub(r"^hu[_-]?", "", label.strip(), flags=re.IGNORECASE)
    text = re.sub(r"(btnclick|btn_click|click)$", "", text, flags=re.IGNORECASE)
    text = text.replace("_", " ")
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    parts = [part.capitalize() for part in text.split() if part]
    return " ".join(parts) if parts else label


def _apply_short_alias(canonical: str, locale_code: AppLocale) -> str:
    cached = _display_alias_cache.get(_cache_key(canonical, locale_code))
    if cached:
        return cached
    if _needs_short_alias(canonical):
        return heuristic_short_alias(canonical)
    return canonical


def display_name_for_event_ref(
    event_ref: str,
    events_index: dict | None,
    *,
    locale: str | None = None,
) -> str:
    """将 CSV 代号 / canonical / 漏斗步骤标签转为用户语言下的展示名。"""
    locale_code = normalize_locale(locale)
    raw = str(event_ref or "").strip()
    if not raw:
        return raw

    step_match = _STEP_PREFIX.match(raw)
    if step_match:
        prefix, body = step_match.group(1), step_match.group(2)
        return f"{prefix} {display_name_for_event_ref(body, events_index, locale=locale_code)}"

    canonical, module, found = resolve_canonical_event_ref(raw, events_index)

    if locale_code == "zh":
        if not found and _looks_like_csv_technical_id(raw):
            return _humanize_csv_label(raw)
        return _apply_short_alias(canonical, locale_code)

    if not _CJK.search(canonical):
        if _looks_like_csv_technical_id(canonical):
            return _humanize_csv_label(canonical)
        return canonical

    short_zh = _apply_short_alias(canonical, "zh")
    translated = _translate_zh_name(short_zh, locale_code)
    mod = _MODULE_EN.get(module, module)
    if mod and mod not in translated:
        return f"{mod} · {translated}"
    return translated


def localized_plan_event_title(
    plan: Any,
    events_index: dict | None,
    *,
    locale: str | None = None,
    suffix: str = "",
) -> str:
    name = display_name_for_event_ref(
        getattr(plan, "matched_event", "") or "",
        events_index,
        locale=locale,
    )
    if suffix:
        return f"{name} · {suffix}"
    return name


def localize_records_for_plan(
    records: list[dict[str, Any]],
    plan: Any,
    events_index: dict | None,
    *,
    locale: str | None = None,
) -> list[dict[str, Any]]:
    if not records or not events_index:
        return records

    keys: set[str] = set()
    dimension = getattr(plan, "dimension", None)
    sub_dimension = getattr(plan, "sub_dimension", None)
    analysis_type = getattr(plan, "analysis_type", None)

    if dimension in (EVENT_NAME_DIMENSION, FUNNEL_STEP_DIMENSION):
        keys.add(str(dimension))
    if sub_dimension == EVENT_NAME_DIMENSION:
        keys.add(str(sub_dimension))
    if analysis_type == "funnel" and dimension:
        keys.add(str(dimension))

    if not keys:
        return records

    localized: list[dict[str, Any]] = []
    for row in records:
        item = dict(row)
        for key in keys:
            if key in item and item[key] is not None:
                item[key] = display_name_for_event_ref(
                    str(item[key]),
                    events_index,
                    locale=locale,
                )
        localized.append(item)
    return localized
