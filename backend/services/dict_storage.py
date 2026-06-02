"""埋点字典读写与内存索引刷新。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from config import EVENTS_DICT_PATH
from services.dict_preprocessor import DictPreprocessor

EventLocation = tuple[int, int]


def load_raw_dictionary(path: Path | None = None) -> dict[str, Any]:
    json_path = path or EVENTS_DICT_PATH
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def save_raw_dictionary(data: dict[str, Any], path: Path | None = None) -> None:
    json_path = path or EVENTS_DICT_PATH
    if "功能列表" not in data or not isinstance(data["功能列表"], list):
        raise ValueError("字典格式无效：缺少「功能列表」")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def reload_events_index(path: Path | None = None) -> dict[str, Any]:
    preprocessor = DictPreprocessor(path or EVENTS_DICT_PATH)
    return preprocessor.index


def find_event_location(data: dict[str, Any], event_name: str) -> EventLocation | None:
    for module_idx, module in enumerate(data.get("功能列表", [])):
        for event_idx, event in enumerate(module.get("事件列表", [])):
            if event.get("事件") == event_name:
                return module_idx, event_idx
    return None


def get_event_raw(data: dict[str, Any], event_name: str) -> dict[str, Any] | None:
    loc = find_event_location(data, event_name)
    if loc is None:
        return None
    module_idx, event_idx = loc
    return deepcopy(data["功能列表"][module_idx]["事件列表"][event_idx])


def update_event_raw(
    data: dict[str, Any],
    event_name: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    loc = find_event_location(data, event_name)
    if loc is None:
        raise ValueError(f"事件不存在: {event_name}")

    module_idx, event_idx = loc
    event = data["功能列表"][module_idx]["事件列表"][event_idx]
    allowed = {"事件触发条件", "事件Data_ID", "属性列表"}
    for key, value in updates.items():
        if key not in allowed:
            continue
        event[key] = value

    return deepcopy(event)


def build_dictionary_tree(data: dict[str, Any]) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    total = 0
    for module in data.get("功能列表", []):
        module_name = module.get("功能", "")
        events: list[dict[str, Any]] = []
        for event in module.get("事件列表", []):
            name = event.get("事件", "")
            if not name:
                continue
            total += 1
            events.append(
                {
                    "name": name,
                    "data_id": event.get("事件Data_ID", ""),
                    "condition": event.get("事件触发条件", ""),
                }
            )
        if module_name:
            modules.append({"name": module_name, "events": events})
    return {
        "source": data.get("来源文件", ""),
        "description": data.get("说明", ""),
        "modules": modules,
        "total_events": total,
    }
