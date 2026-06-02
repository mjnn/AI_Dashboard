"""DeepSeek 模型选择（持久化于 data/llm_settings.json）。"""

from __future__ import annotations

import json
from typing import Literal

from config import DATA_DIR

DeepSeekModelId = Literal["deepseek-v4-flash", "deepseek-v4-pro"]

DEFAULT_DEEPSEEK_MODEL: DeepSeekModelId = "deepseek-v4-flash"
ALLOWED_DEEPSEEK_MODELS: tuple[DeepSeekModelId, ...] = (
    "deepseek-v4-flash",
    "deepseek-v4-pro",
)

_MODEL_LABELS: dict[str, str] = {
    "deepseek-v4-flash": "DeepSeek V4 Flash（更快）",
    "deepseek-v4-pro": "DeepSeek V4 Pro（更准）",
}

_SETTINGS_PATH = DATA_DIR / "llm_settings.json"


def _normalize_model(model: str) -> DeepSeekModelId:
    cleaned = model.strip()
    if cleaned not in ALLOWED_DEEPSEEK_MODELS:
        raise ValueError(
            f"不支持的模型: {model}，可选: {', '.join(ALLOWED_DEEPSEEK_MODELS)}"
        )
    return cleaned  # type: ignore[return-value]


def get_deepseek_model() -> DeepSeekModelId:
    if not _SETTINGS_PATH.exists():
        return DEFAULT_DEEPSEEK_MODEL
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return _normalize_model(str(data.get("model", DEFAULT_DEEPSEEK_MODEL)))
    except (OSError, json.JSONDecodeError, ValueError):
        return DEFAULT_DEEPSEEK_MODEL


def set_deepseek_model(model: str) -> DeepSeekModelId:
    normalized = _normalize_model(model)
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump({"model": normalized}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return normalized


def list_deepseek_model_options() -> list[dict[str, str]]:
    current = get_deepseek_model()
    return [
        {
            "id": model_id,
            "label": _MODEL_LABELS[model_id],
            "selected": model_id == current,
        }
        for model_id in ALLOWED_DEEPSEEK_MODELS
    ]
