"""分析链路性能测试 — 与功能覆盖测试一并收敛。

运行：
  cd backend && python -m pytest tests/test_analysis_performance.py -k "not llm" -v
  cd backend && python -m pytest tests/test_analysis_performance.py -v   # 含 LLM（需 Key）
  ANALYSIS_PERF_LLM=0 python -m pytest tests/test_analysis_performance.py -v  # 跳过 LLM 性能
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config import EVENTS_DICT_PATH, get_deepseek_api_key  # noqa: E402
from schemas.analysis import (  # noqa: E402
    AnalysisPlan,
    MetricDef,
    StatisticalCaliber,
    TimeRange,
    VisualizationDef,
)
from services.analysis_registry import (  # noqa: E402
    ANALYSIS_CATALOG,
    normalize_plan_for_analysis,
)
from services.analysis_route_memory import clear_route_cache  # noqa: E402
from services.csv_processor import (  # noqa: E402
    invalidate_data_pool_cache,
    load_data_pool,
    process_csv,
)
from services.data_profiler import list_distinct_csv_events  # noqa: E402
from services.dict_preprocessor import DictPreprocessor  # noqa: E402
from services.event_cluster_discovery import EventCluster, EventClusterDiscovery  # noqa: E402
from services.field_resolver import resolve_event  # noqa: E402
from services.multi_event_analysis import run_comprehensive_analysis  # noqa: E402
from tests.fixtures.performance_budgets import load_budgets, perf_llm_enabled  # noqa: E402
from tests.fixtures.performance_scenarios import (  # noqa: E402
    LLM_PERF_SCENARIOS,
    PERF_SCENARIOS,
)
from tests.fixtures.plan_factory import build_plan_for_type, event_filter_for_type  # noqa: E402


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class TestDataPoolPerformance(unittest.TestCase):
    """CSV 数据池：冷加载 vs 缓存命中。"""

    def tearDown(self):
        invalidate_data_pool_cache()

    def test_cold_load_within_budget(self):
        budgets = load_budgets()
        invalidate_data_pool_cache()
        t0 = time.perf_counter()
        df = load_data_pool(force_reload=True)
        elapsed = _ms(t0)
        self.assertGreater(len(df), 1000)
        self.assertLessEqual(
            elapsed,
            budgets.data_pool_cold_ms,
            msg=f"cold load {elapsed}ms > budget {budgets.data_pool_cold_ms}ms",
        )

    def test_cached_load_faster_than_cold(self):
        budgets = load_budgets()
        invalidate_data_pool_cache()
        t0 = time.perf_counter()
        first = load_data_pool(force_reload=True)
        cold_ms = _ms(t0)

        t1 = time.perf_counter()
        second = load_data_pool()
        warm_ms = _ms(t1)

        self.assertIs(first, second)
        self.assertLessEqual(
            warm_ms,
            budgets.data_pool_cached_ms,
            msg=f"cached {warm_ms}ms > budget {budgets.data_pool_cached_ms}ms",
        )
        if cold_ms > budgets.data_pool_cached_ms:
            speedup = cold_ms / max(warm_ms, 1)
            self.assertGreaterEqual(
                speedup,
                budgets.data_pool_cache_speedup_min,
                msg=f"speedup {speedup:.1f}x < min {budgets.data_pool_cache_speedup_min}x "
                f"(cold={cold_ms}ms warm={warm_ms}ms)",
            )


class TestProcessCsvPerformance(unittest.TestCase):
    """各 analysis_type 单次 process_csv 耗时。"""

    @classmethod
    def setUpClass(cls):
        cls.budgets = load_budgets()
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.df = load_data_pool()
        cls.csv_events = list_distinct_csv_events(cls.df)
        cls.event_def = resolve_event(
            "Carlog_进入",
            cls.index,
            csv_event_names=cls.csv_events,
            query="",
        ).event_def
        cls._may_be_empty = {"summary_kpi", "repeat_rate", "stickiness"}

    def test_each_analysis_type_within_budget(self):
        failures: list[str] = []
        for spec in ANALYSIS_CATALOG:
            at = spec["id"]
            t0 = time.perf_counter()
            try:
                plan = normalize_plan_for_analysis(
                    build_plan_for_type(at, chart_type=spec["default_chart"]),
                    query=spec["example_query"],
                )
                data_df, execution = process_csv(
                    plan,
                    self.event_def,
                    df=self.df,
                    events_index=self.index,
                    event_filter_override=event_filter_for_type(at),
                )
                elapsed = _ms(t0)
                exec_ms = execution.execution_time_ms
                if elapsed > self.budgets.process_csv_type_ms:
                    failures.append(
                        f"{at}: wall={elapsed}ms exec={exec_ms}ms "
                        f"> {self.budgets.process_csv_type_ms}ms"
                    )
                elif execution.status != "success":
                    failures.append(f"{at}: status={execution.status}")
                elif data_df.empty and at not in self._may_be_empty:
                    failures.append(f"{at}: empty")
            except Exception as exc:
                failures.append(f"{at}: {exc}")
        self.assertFalse(failures, "\n".join(failures))

    def test_all_types_aggregate_within_budget(self):
        budgets = load_budgets()
        t0 = time.perf_counter()
        count = 0
        for spec in ANALYSIS_CATALOG:
            plan = normalize_plan_for_analysis(
                build_plan_for_type(spec["id"]),
                query=spec["example_query"],
            )
            process_csv(
                plan,
                self.event_def,
                df=self.df,
                events_index=self.index,
                event_filter_override=event_filter_for_type(spec["id"]),
            )
            count += 1
        elapsed = _ms(t0)
        self.assertEqual(count, len(ANALYSIS_CATALOG))
        self.assertLessEqual(
            elapsed,
            budgets.process_csv_all_types_ms,
            msg=f"all {count} types took {elapsed}ms > {budgets.process_csv_all_types_ms}ms",
        )


class TestComprehensivePipelinePerformance(unittest.TestCase):
    """多事件综合看板（无 LLM narrator / Agent）。"""

    @classmethod
    def setUpClass(cls):
        cls.budgets = load_budgets()
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.df = load_data_pool()
        cls.csv_events = list_distinct_csv_events(cls.df)
        cls.columns = list(cls.df.columns)
        cls.event_def = resolve_event(
            "Carlog_进入",
            cls.index,
            csv_event_names=cls.csv_events,
            query="综合分析一下carlog",
        ).event_def
        cls.scope = {"carlog_entry", "carlog_record", "carlog_exit"}
        cls.discovery = EventClusterDiscovery(
            primary_cluster_id="carlog_flow",
            clusters=[
                EventCluster(
                    id="carlog_flow",
                    name="Carlog 使用链路",
                    rationale="进入/录制/退出同属 Carlog",
                    csv_events=sorted(cls.scope),
                    funnel_order=["carlog_entry", "carlog_record", "carlog_exit"],
                    analysis_angles=["对比 UV", "趋势"],
                )
            ],
            anchor_event="Carlog_进入",
            source="rules_fallback",
        )
        cls.seed = AnalysisPlan(
            analysis_type="event_comparison",
            matched_event="Carlog_进入",
            matched_module="Carlog",
            match_confidence="high",
            metrics=[MetricDef(id="pv", name="PV", type="count")],
            visualization=VisualizationDef(
                chart_type="bar", layout="single", reasoning="perf"
            ),
            dimension="event",
            filters={},
            time_range=TimeRange(type="last_n_days", value=30),
            statistical_caliber=StatisticalCaliber(
                dedup_method="按VIN去重",
                time_granularity="daily",
                description="perf",
            ),
        )

    def test_comprehensive_pipeline_within_budget(self):
        t0 = time.perf_counter()
        resp = run_comprehensive_analysis(
            self.seed,
            self.event_def,
            self.df,
            self.columns,
            query="综合分析一下carlog",
            user_mode="auto",
            events_index=self.index,
            csv_event_names=self.csv_events,
            event_filter_override=self.scope,
            cluster_discovery=self.discovery,
            locale="zh",
        )
        elapsed = _ms(t0)
        self.assertGreaterEqual(resp.panel_count, 2)
        self.assertLessEqual(
            elapsed,
            self.budgets.comprehensive_pipeline_ms,
            msg=f"comprehensive pipeline {elapsed}ms > "
            f"{self.budgets.comprehensive_pipeline_ms}ms "
            f"(panels={resp.panel_count})",
        )
        if resp.execution.execution_time_ms:
            self.assertLessEqual(
                resp.execution.execution_time_ms,
                self.budgets.comprehensive_pipeline_ms,
            )


@unittest.skipUnless(
    get_deepseek_api_key() and perf_llm_enabled(),
    "需要 DEEPSEEK_API_KEY 且 ANALYSIS_PERF_LLM!=0",
)
class TestAnalyzeApiPerformance(unittest.TestCase):
    """端到端 /api/analyze 墙钟预算（冷 / 暖缓存）。"""

    @classmethod
    def setUpClass(cls):
        from contextlib import ExitStack
        from fastapi.testclient import TestClient
        from main import app

        cls.budgets = load_budgets()
        cls._stack = ExitStack()
        cls.client = cls._stack.enter_context(TestClient(app))

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def setUp(self):
        clear_route_cache()

    def tearDown(self):
        clear_route_cache()

    def _post_analyze(self, query: str) -> tuple[dict, int]:
        t0 = time.perf_counter()
        r = self.client.post(
            "/api/analyze",
            json={"query": query, "analysis_mode": "auto", "locale": "zh"},
        )
        elapsed = _ms(t0)
        self.assertEqual(r.status_code, 200, msg=r.text[:400])
        return r.json(), elapsed

    def test_llm_perf_scenarios(self):
        for scenario in LLM_PERF_SCENARIOS:
            query = scenario.queries[0]
            with self.subTest(scenario=scenario.id, phase="cold", query=query):
                clear_route_cache()
                data, cold_ms = self._post_analyze(query)
                self.assertGreater(data.get("execution", {}).get("filtered_rows", 0), 0)
                self.assertLessEqual(
                    cold_ms,
                    scenario.max_wall_ms,
                    msg=f"cold {cold_ms}ms > {scenario.max_wall_ms}ms",
                )
                print(f"  [perf cold] {scenario.id}: {cold_ms}ms mode={data.get('mode')}")

            if scenario.warm_max_wall_ms is not None:
                warm_query = scenario.queries[-1]
                with self.subTest(scenario=scenario.id, phase="warm", query=warm_query):
                    data, warm_ms = self._post_analyze(warm_query)
                    self.assertLessEqual(
                        warm_ms,
                        scenario.warm_max_wall_ms,
                        msg=f"warm {warm_ms}ms > {scenario.warm_max_wall_ms}ms",
                    )
                    print(
                        f"  [perf warm] {scenario.id}: {warm_ms}ms "
                        f"mode={data.get('mode')} panels={data.get('panel_count')}"
                    )


class TestPerformanceScenarioRegistry(unittest.TestCase):
    def test_perf_scenarios_have_budgets(self):
        for s in PERF_SCENARIOS:
            self.assertGreater(s.max_wall_ms, 0, msg=s.id)
            if s.tier == "llm":
                self.assertGreaterEqual(len(s.queries), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
