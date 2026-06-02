"""埋点字典预处理服务。"""

from __future__ import annotations

import json
import re
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Optional


def _normalize_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name.lower())


def _extract_aliases(event_name: str, module_name: str) -> List[str]:
    """从事件名提取关键词别名，含后排_前缀时关联模块名。"""
    aliases: set[str] = {event_name}

    if event_name.startswith("后排_"):
        aliases.add(module_name)
        aliases.add(event_name.removeprefix("后排_"))

    parts = re.split(r"[_\-/\\|]+", event_name)
    for part in parts:
        part = part.strip()
        if len(part) >= 2:
            aliases.add(part)

    compact = event_name.replace("_", "").replace(" ", "")
    if compact:
        aliases.add(compact)

    if module_name and module_name.lower() in event_name.lower():
        aliases.add(module_name)

    return sorted(aliases, key=len, reverse=True)


class DictPreprocessor:
    """加载并扁平化埋点字典，提供事件查询接口。"""

    def __init__(self, json_path: Optional[Path] = None) -> None:
        self._json_path = json_path
        self._events: Dict[str, dict] = {}
        self._event_names: List[str] = []
        self._modules: List[dict] = []
        self._alias_index: Dict[str, str] = {}
        self._normalized_index: Dict[str, str] = {}

        if json_path is not None:
            self.load(json_path)

    def load(self, json_path: Path) -> None:
        """加载 JSON 字典并构建内存索引。"""
        self._json_path = json_path
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)

        events: Dict[str, dict] = {}
        modules: List[dict] = []
        alias_index: Dict[str, str] = {}
        normalized_index: Dict[str, str] = {}

        for module in raw.get("功能列表", []):
            module_name = module.get("功能", "")
            module_events: List[str] = []

            for event in module.get("事件列表", []):
                event_name = event.get("事件", "")
                if not event_name:
                    continue

                attributes: Dict[str, dict] = {}
                for attr in event.get("属性列表", []):
                    prop_name = attr.get("事件的属性", "")
                    if not prop_name:
                        continue
                    desc = attr.get("属性值的描述")
                    attributes[prop_name] = {
                        "cn_name": attr.get("属性中文说明", ""),
                        "description": desc,
                    }

                aliases = _extract_aliases(event_name, module_name)
                for attr in event.get("属性列表", []):
                    for item in attr.get("属性值的描述") or []:
                        if isinstance(item, dict):
                            label = item.get("label")
                            if label:
                                aliases.append(str(label))
                aliases = list(dict.fromkeys(aliases))
                event_def = {
                    "module": module_name,
                    "data_id": event.get("事件Data_ID", ""),
                    "condition": event.get("事件触发条件", ""),
                    "attributes": attributes,
                    "aliases": aliases,
                }
                events[event_name] = event_def
                module_events.append(event_name)

                csv_labels: set[str] = set()
                for attr in event.get("属性列表", []):
                    for item in attr.get("属性值的描述") or []:
                        if isinstance(item, dict) and item.get("label"):
                            csv_labels.add(str(item["label"]))

                for alias in aliases:
                    if str(alias) in csv_labels:
                        alias_index[alias] = event_name
                        normalized_index[_normalize_name(alias)] = event_name
                        lower = str(alias).lower()
                        if lower != alias:
                            alias_index[lower] = event_name
                            normalized_index[_normalize_name(lower)] = event_name
                    else:
                        alias_index.setdefault(alias, event_name)
                        normalized_index.setdefault(_normalize_name(alias), event_name)
                        lower = str(alias).lower()
                        if lower != alias:
                            alias_index.setdefault(lower, event_name)
                            normalized_index.setdefault(_normalize_name(lower), event_name)

                normalized_index[_normalize_name(event_name)] = event_name
                alias_index.setdefault(event_name.lower(), event_name)

            if module_name:
                modules.append({"name": module_name, "events": module_events})

        self._events = events
        self._event_names = sorted(events.keys())
        self._modules = modules
        self._alias_index = alias_index
        self._normalized_index = normalized_index

    @property
    def index(self) -> dict:
        """返回完整内存索引。"""
        return {
            "events": self._events,
            "event_names": self._event_names,
            "modules": self._modules,
            "alias_index": self._alias_index,
            "normalized_index": self._normalized_index,
        }

    def get_all_event_names(self) -> List[str]:
        """返回全部事件名，供 LLM 白名单使用。"""
        return list(self._event_names)

    def find_event(self, name: str) -> Optional[dict]:
        """查找事件定义，支持精确匹配、别名匹配与模糊匹配。"""
        if not name:
            return None

        if name in self._events:
            return {"event_name": name, **self._events[name]}

        if name in self._alias_index:
            canonical = self._alias_index[name]
            return {"event_name": canonical, **self._events[canonical]}

        normalized = _normalize_name(name)
        if normalized in self._normalized_index:
            canonical = self._normalized_index[normalized]
            return {"event_name": canonical, **self._events[canonical]}

        for event_name in self._event_names:
            if name in event_name or event_name in name:
                return {"event_name": event_name, **self._events[event_name]}

        for event_name, event_def in self._events.items():
            for alias in event_def["aliases"]:
                if name in alias or alias in name:
                    return {"event_name": event_name, **event_def}

        close = get_close_matches(name, self._event_names, n=1, cutoff=0.6)
        if close:
            canonical = close[0]
            return {"event_name": canonical, **self._events[canonical]}

        normalized_candidates = {
            _normalize_name(n): n for n in self._event_names
        }
        close_norm = get_close_matches(
            normalized, list(normalized_candidates.keys()), n=1, cutoff=0.75
        )
        if close_norm:
            canonical = normalized_candidates[close_norm[0]]
            return {"event_name": canonical, **self._events[canonical]}

        return None

    def get_modules_list(self) -> List[dict]:
        """返回按模块分组的事件列表。"""
        return [dict(module) for module in self._modules]


def load_dict_preprocessor(json_path: Path) -> DictPreprocessor:
    """加载字典预处理器。"""
    processor = DictPreprocessor()
    processor.load(json_path)
    return processor
