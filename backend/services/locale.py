"""Locale helpers for LLM user-facing output."""

from __future__ import annotations

from typing import Literal

AppLocale = Literal["zh", "en", "de"]
DEFAULT_LOCALE: AppLocale = "zh"

_INSTRUCTIONS: dict[AppLocale, str] = {
    "zh": (
        "所有面向用户的文案（标题、摘要、洞察、聚类名称、推荐理由、图表标题等）"
        "必须使用简体中文。"
    ),
    "en": (
        "All user-facing text (titles, summaries, insights, cluster names, "
        "recommendation reasons, chart titles, etc.) must be in English."
    ),
    "de": (
        "Alle nutzerorientierten Texte (Titel, Zusammenfassungen, Erkenntnisse, "
        "Cluster-Namen, Empfehlungsgründe, Diagrammtitel usw.) müssen auf Deutsch sein."
    ),
}


def normalize_locale(value: str | None) -> AppLocale:
    if value in _INSTRUCTIONS:
        return value  # type: ignore[return-value]
    if value:
        short = value.split("-")[0].lower()
        if short in _INSTRUCTIONS:
            return short  # type: ignore[return-value]
    return DEFAULT_LOCALE


def locale_instruction(locale: str | None) -> str:
    code = normalize_locale(locale)
    return f"\n\n## Language / 语言 / Sprache\n{_INSTRUCTIONS[code]}\n"
