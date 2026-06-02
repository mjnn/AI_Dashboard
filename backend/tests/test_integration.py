"""集成测试 — 不依赖 LLM 的用例本地跑；需 LLM 的用例在 DEEPSEEK_API_KEY 存在时执行。"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

# 保证从 backend 目录可 import
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config import get_deepseek_api_key  # noqa: E402
from services.csv_processor import load_data_pool, process_csv  # noqa: E402
from services.data_profiler import build_data_profile, list_distinct_csv_events  # noqa: E402
from services.dict_preprocessor import DictPreprocessor  # noqa: E402
from services.event_mapping import (
    build_dict_csv_mapping_hint,
    repair_plan_event_adaptation,
    resolve_event_filter,
    sanitize_csv_event_filter,
)  # noqa: E402
from services.event_scope import infer_related_csv_events  # noqa: E402
from services.field_resolver import resolve_event, resolve_column_name  # noqa: E402
from config import EVENTS_DICT_PATH  # noqa: E402


class TestDataPool(unittest.TestCase):
    def test_load_data_pool_has_rows(self):
        df = load_data_pool()
        self.assertGreater(len(df), 1000)

    def test_event_column_exists(self):
        df = load_data_pool()
        cols = {c.lower() for c in df.columns}
        self.assertTrue("event" in cols or any("event" in c for c in cols))

    def test_distinct_csv_events(self):
        df = load_data_pool()
        events = list_distinct_csv_events(df)
        self.assertIn("carlog_entry", events)

    def test_data_profile(self):
        profile = build_data_profile()
        self.assertGreater(profile["total_rows"], 0)
        self.assertIn("feasible_analysis_types", profile)


class TestFieldResolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.csv_events = list_distinct_csv_events(load_data_pool())

    def test_carlog_resolves_to_entry(self):
        r = resolve_event(
            "carlog", self.index, csv_event_names=self.csv_events, query="carlog"
        )
        self.assertEqual(r.event_name, "Carlog_进入")

    def test_carlog_enter_variants(self):
        for name in ("Carlog进入", "carlog_entry", "Carlog_进入"):
            r = resolve_event(
                name, self.index, csv_event_names=self.csv_events, query="carlog"
            )
            self.assertEqual(r.event_name, "Carlog_进入", msg=name)

    def test_carlog_chinese_prefix_resolves(self):
        idx = self.index
        csv_events = self.csv_events
        r = resolve_event(
            "分析carlog", idx, csv_event_names=csv_events, query="分析carlog"
        )
        self.assertEqual(r.event_name, "Carlog_进入")
        related = infer_related_csv_events("分析carlog", csv_events)
        self.assertIsNotNone(related)
        self.assertIn("carlog_entry", related)

    def test_resolve_vin_column(self):
        df = load_data_pool()
        col = resolve_column_name("vin_code", list(df.columns), {})
        self.assertIsNotNone(col)
        self.assertIn("vin", col.lower())


class TestEventMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.csv_events = list_distinct_csv_events(load_data_pool())

    def test_mapping_hint_contains_carlog(self):
        hint = build_dict_csv_mapping_hint(self.index, self.csv_events)
        self.assertIn("Carlog_进入", hint)
        self.assertIn("carlog_entry", hint)

    def test_sanitize_csv_event_filter(self):
        out = sanitize_csv_event_filter(
            ["carlog_entry", "fake_event"], self.csv_events
        )
        self.assertEqual(out, ["carlog_entry"])

    def test_resolve_event_filter_llm_priority(self):
        filt, source = resolve_event_filter(
            csv_event_filter=["carlog_entry", "carlog_exit"],
            matched_event="Carlog_进入",
            comparison_events=None,
            events_index=self.index,
            csv_event_names=self.csv_events,
            query="分析carlog",
        )
        self.assertEqual(source, "llm_csv_filter")
        self.assertIn("carlog_entry", filt)
        self.assertIn("carlog_exit", filt)

    def test_repair_respects_llm_csv_filter(self):
        data = repair_plan_event_adaptation(
            {
                "matched_event": "自动剪辑",
                "match_confidence": "high",
                "csv_event_filter": [
                    "carlog_entry",
                    "carlog_exit",
                    "carlog_record",
                    "carlog_autocut",
                    "carlog_video_edit",
                ],
            },
            self.index,
            self.csv_events,
            "分析carlog",
        )
        self.assertEqual(data["matched_event"], "Carlog_进入")
        self.assertGreaterEqual(len(data["csv_event_filter"]), 3)


class TestProcessCsv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.df = load_data_pool()
        cls.csv_events = list_distinct_csv_events(cls.df)
        cls.event_def = resolve_event(
            "Carlog_进入", cls.index, csv_event_names=cls.csv_events, query=""
        ).event_def

    def _minimal_plan(self):
        from schemas.analysis import (
            AnalysisPlan,
            MetricDef,
            StatisticalCaliber,
            TimeRange,
            VisualizationDef,
        )

        return AnalysisPlan(
            analysis_type="time_series",
            matched_event="Carlog_进入",
            matched_module="Carlog",
            match_confidence="high",
            metrics=[MetricDef(id="pv", name="PV", type="count")],
            visualization=VisualizationDef(
                chart_type="line", layout="single", reasoning="test"
            ),
            dimension="date",
            filters={},
            time_range=TimeRange(type="last_n_days", value=30),
            statistical_caliber=StatisticalCaliber(
                dedup_method="none",
                time_granularity="daily",
                description="test",
            ),
        )

    def test_time_series_with_pool_override(self):
        plan = self._minimal_plan()
        filt = infer_related_csv_events("carlog", self.csv_events)
        result, execution = process_csv(
            plan,
            self.event_def,
            df=self.df,
            event_filter_override=filt,
        )
        self.assertEqual(execution.status, "success")
        self.assertGreater(execution.filtered_rows, 0)
        self.assertFalse(result.empty)


class TestApiNoLlm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from contextlib import ExitStack
        from fastapi.testclient import TestClient
        from main import app

        cls._stack = ExitStack()
        cls.client = cls._stack.enter_context(TestClient(app))

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("data_pool_ready"))
        self.assertGreater(data.get("event_count", 0), 1000)

    def test_events(self):
        r = self.client.get("/api/events")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.json()["total_events"], 1000)

    def test_analysis_types(self):
        r = self.client.get("/api/analysis-types")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["total"], 15)

    def test_analyze_empty_query_rejected(self):
        r = self.client.post("/api/analyze", json={"query": ""})
        self.assertIn(r.status_code, (422, 400))

    def test_csv_files_removed(self):
        r = self.client.get("/api/csv-files")
        self.assertEqual(r.status_code, 404)


@unittest.skipUnless(get_deepseek_api_key(), "需要 DEEPSEEK_API_KEY")
class TestApiWithLlm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from contextlib import ExitStack
        from fastapi.testclient import TestClient
        from main import app

        cls._stack = ExitStack()
        cls.client = cls._stack.enter_context(TestClient(app))

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def test_recommendations(self):
        r = self.client.get("/api/recommendations")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data["recommendations"]), 3)
        self.assertGreater(data["data_summary"]["total_rows"], 0)

    def _analyze(self, query: str, mode: str = "auto"):
        t0 = time.perf_counter()
        r = self.client.post(
            "/api/analyze",
            json={"query": query, "analysis_mode": mode},
        )
        elapsed = time.perf_counter() - t0
        self.assertEqual(
            r.status_code,
            200,
            msg=f"{query!r} {mode} -> {r.status_code} {r.text[:300]}",
        )
        data = r.json()
        self.assertIn(data["mode"], ("single", "exploratory"))
        self.assertGreater(data["execution"]["filtered_rows"], 0, msg=query)
        return data, elapsed

    def test_analyze_carlog_auto(self):
        data, elapsed = self._analyze("carlog")
        self.assertEqual(data["plan"]["matched_event"], "Carlog_进入")
        self.assertGreater(data["execution"]["filtered_rows"], 0)
        if data["mode"] == "exploratory":
            self.assertGreaterEqual(data.get("panel_count", 0), 1)
        print(f"  carlog auto: mode={data['mode']} panels={data.get('panel_count')} elapsed={elapsed:.1f}s")

    def test_analyze_carlog_chinese_prefix(self):
        data, _ = self._analyze("分析carlog")
        self.assertEqual(
            data["plan"]["matched_event"],
            "Carlog_进入",
            msg="模块级中文问题不应落到自动剪辑",
        )
        self.assertGreater(data["execution"]["filtered_rows"], 50000)

    def test_analyze_carlog_precise(self):
        data, _ = self._analyze("Carlog进入最近7天每日趋势", "precise")
        self.assertEqual(data["mode"], "single")
        self.assertIsNotNone(data.get("chart_config"))

    def test_analyze_exploratory_mode(self):
        data, elapsed = self._analyze("全面分析一下carlog", "exploratory")
        self.assertEqual(data["mode"], "exploratory")
        self.assertGreaterEqual(data.get("panel_count", 0), 2, msg=f"elapsed={elapsed:.1f}s")

    def test_analyze_usage_retention(self):
        data, _ = self._analyze("carlog使用1次和2次的车辆数", "precise")
        self.assertEqual(data["mode"], "single")
        self.assertGreater(len(data.get("chart_config", {}).get("data", []) or []), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
