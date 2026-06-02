"""分析类型 / 图表类型 / 多提示词 覆盖测试。

运行：
  cd backend && python tests/run_analysis_convergence.py              # 功能 + 性能 收敛
  cd backend && python -m pytest tests/test_analysis_coverage.py -v
  cd backend && python -m pytest tests/test_analysis_performance.py -k "not llm" -v

LLM 场景需 DEEPSEEK_API_KEY：
  cd backend && python -m pytest tests/test_analysis_coverage.py -v
  cd backend && python -m pytest tests/test_analysis_performance.py -v
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
from schemas.analysis import AnalysisPlan  # noqa: E402
from services.analysis_intent import infer_scope_mode_fallback  # noqa: E402
from services.analysis_registry import (  # noqa: E402
    ANALYSIS_CATALOG,
    ANALYSIS_TYPE_IDS,
    CHART_TYPE_CATALOG,
    CHART_TYPE_IDS,
    get_allowed_chart_types,
    normalize_plan_for_analysis,
    repair_funnel_analysis_plan,
    repair_usage_retention_plan,
)
from services.chart_builder import build  # noqa: E402
from services.csv_processor import load_data_pool, process_csv  # noqa: E402
from services.data_profiler import list_distinct_csv_events  # noqa: E402
from services.dict_preprocessor import DictPreprocessor  # noqa: E402
from services.field_resolver import resolve_event  # noqa: E402
from services.llm_planner import repair_plan_llm_payload  # noqa: E402
from tests.fixtures.analysis_scenarios import (  # noqa: E402
    ALL_QUERY_SCENARIOS,
    LLM_SCENARIOS,
    REPAIR_SCENARIOS,
    Expectation,
    QueryScenario,
)
from tests.fixtures.plan_factory import (  # noqa: E402
    build_plan_for_type,
    event_filter_for_type,
)


def _apply_repair(scenario: QueryScenario, query: str, payload: dict, ctx) -> dict:
    data = dict(payload)
    for step in scenario.repair_pipeline:
        if step == "repair_plan_llm_payload":
            data = repair_plan_llm_payload(
                data,
                query=query,
                csv_event_names=ctx["csv_events"],
                events_index=ctx["index"],
            )
        elif step == "repair_funnel_analysis_plan":
            data = repair_funnel_analysis_plan(
                data,
                query,
                csv_event_names=ctx["csv_events"],
                events_index=ctx["index"],
            )
        elif step == "repair_usage_retention_plan":
            data = repair_usage_retention_plan(
                data,
                query,
                csv_event_names=ctx["csv_events"],
                events_index=ctx["index"],
            )
        else:
            raise ValueError(f"unknown repair step: {step}")
    return data


def _assert_expectation(
    testcase: unittest.TestCase,
    expect: Expectation,
    *,
    payload: dict | None = None,
    plan: AnalysisPlan | None = None,
    response: dict | None = None,
) -> None:
    if payload is not None:
        if expect.analysis_type is not None:
            testcase.assertEqual(payload.get("analysis_type"), expect.analysis_type)
        if expect.chart_type is not None:
            testcase.assertEqual(
                (payload.get("visualization") or {}).get("chart_type"),
                expect.chart_type,
            )
        if expect.dimension is not None:
            testcase.assertEqual(payload.get("dimension"), expect.dimension)
        if expect.csv_event_filter is not None:
            testcase.assertEqual(payload.get("csv_event_filter"), expect.csv_event_filter)
        for bad in expect.csv_event_filter_excludes:
            testcase.assertNotIn(bad, payload.get("csv_event_filter") or [])
        if expect.no_comparison_events:
            testcase.assertIsNone(payload.get("comparison_events"))

    if plan is not None:
        if expect.analysis_type is not None:
            testcase.assertEqual(plan.analysis_type, expect.analysis_type)
        if expect.chart_type is not None:
            testcase.assertEqual(plan.visualization.chart_type, expect.chart_type)
        allowed = expect.chart_type_in
        if allowed:
            testcase.assertIn(plan.visualization.chart_type, allowed)

    if response is not None:
        if expect.mode is not None:
            testcase.assertEqual(response.get("mode"), expect.mode)
        modes = expect.mode_in
        if modes:
            testcase.assertIn(response.get("mode"), modes)
        plan_data = response.get("plan") or {}
        if expect.analysis_type is not None:
            testcase.assertEqual(plan_data.get("analysis_type"), expect.analysis_type)
        if expect.matched_event is not None:
            testcase.assertEqual(plan_data.get("matched_event"), expect.matched_event)
        if expect.matched_event_contains is not None:
            testcase.assertIn(
                expect.matched_event_contains,
                plan_data.get("matched_event") or "",
            )
        chart = response.get("chart_config") or {}
        if expect.chart_type is not None:
            testcase.assertEqual(chart.get("chart_type"), expect.chart_type)
        allowed = expect.chart_type_in
        if allowed:
            ct = chart.get("chart_type") or (plan_data.get("visualization") or {}).get(
                "chart_type"
            )
            testcase.assertIn(ct, allowed)
        execution = response.get("execution") or {}
        if expect.min_filtered_rows:
            testcase.assertGreaterEqual(
                execution.get("filtered_rows", 0),
                expect.min_filtered_rows,
                msg=f"filtered_rows={execution.get('filtered_rows')}",
            )
        if expect.min_panel_count:
            testcase.assertGreaterEqual(
                response.get("panel_count", 0),
                expect.min_panel_count,
            )
        points = chart.get("data") or []
        if expect.min_chart_points and response.get("mode") == "single":
            testcase.assertGreaterEqual(len(points), expect.min_chart_points)


class TestAnalysisTypeCatalog(unittest.TestCase):
    """注册表完整性：analysis_type 与 chart_type 枚举不遗漏。"""

    def test_all_analysis_types_have_factory_plan(self):
        for spec in ANALYSIS_CATALOG:
            plan = build_plan_for_type(spec["id"])
            self.assertEqual(plan.analysis_type, spec["id"])

    def test_chart_types_covered_by_catalog(self):
        covered: set[str] = set()
        for spec in ANALYSIS_CATALOG:
            covered.update(spec["chart_types"])
        missing = CHART_TYPE_IDS - covered
        self.assertFalse(missing, msg=f"chart types not in any analysis spec: {missing}")


class TestAnalysisTypePipeline(unittest.TestCase):
    """每种 analysis_type：normalize → process_csv → build 图表。"""

    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.df = load_data_pool()
        cls.csv_events = list_distinct_csv_events(cls.df)
        cls.event_def = resolve_event(
            "Carlog_进入",
            cls.index,
            csv_event_names=cls.csv_events,
            query="",
        ).event_def
        # 单行 KPI 类允许空表
        cls._may_be_empty = {"summary_kpi", "repeat_rate", "stickiness"}

    def test_each_analysis_type_pipeline(self):
        failures: list[str] = []
        for spec in ANALYSIS_CATALOG:
            at = spec["id"]
            try:
                raw = build_plan_for_type(at, chart_type=spec["default_chart"])
                plan = normalize_plan_for_analysis(raw, query=spec["example_query"])
                filt = event_filter_for_type(at)
                data_df, execution = process_csv(
                    plan,
                    self.event_def,
                    df=self.df,
                    events_index=self.index,
                    event_filter_override=filt,
                )
                if execution.status != "success":
                    failures.append(f"{at}: status={execution.status}")
                    continue
                if data_df.empty and at not in self._may_be_empty:
                    failures.append(f"{at}: empty result")
                    continue
                records = data_df.to_dict(orient="records")
                chart = build(plan, records, events_index=self.index, locale="zh")
                self.assertIsNotNone(chart.chart_type)
                self.assertTrue(chart.title)
            except Exception as exc:
                failures.append(f"{at}: {exc}")
        self.assertFalse(failures, "\n".join(failures))


class TestChartTypeRendering(unittest.TestCase):
    """每种 chart_type 至少渲染一次 ChartConfig。"""

    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index

    def test_each_chart_type_renders(self):
        missing: list[str] = []
        for chart_type in sorted(CHART_TYPE_IDS):
            host_type = None
            for spec in ANALYSIS_CATALOG:
                if chart_type in spec["chart_types"]:
                    host_type = spec["id"]
                    break
            if not host_type:
                missing.append(chart_type)
                continue
            plan = normalize_plan_for_analysis(
                build_plan_for_type(host_type, chart_type=chart_type),
                query="coverage",
            )
            self.assertEqual(plan.visualization.chart_type, chart_type)
            sample = self._sample_records(plan)
            chart = build(plan, sample, events_index=self.index, locale="zh")
            self.assertIsNotNone(chart.chart_type)
            self.assertTrue(chart.title)
        self.assertFalse(missing, f"no host analysis_type for charts: {missing}")

    @staticmethod
    def _sample_records(plan: AnalysisPlan) -> list[dict]:
        dim = plan.dimension
        if plan.visualization.chart_type == "funnel_chart":
            return [
                {"漏斗步骤": "进入", "user_count": 100, "conversion_rate": 100},
                {"漏斗步骤": "录制", "user_count": 60, "conversion_rate": 60},
            ]
        if plan.visualization.chart_type == "gauge":
            return [{"_summary": "整体", "stickiness": 0.42, "repeat_rate": 0.35}]
        if plan.visualization.chart_type == "heatmap":
            return [
                {"date": "2026-01-01", "时段": "09:00", "pv": 10},
                {"date": "2026-01-01", "时段": "10:00", "pv": 20},
            ]
        if plan.visualization.chart_type == "pie":
            return [
                {dim: "A", plan.metrics[0].id: 30},
                {dim: "B", plan.metrics[0].id: 70},
            ]
        return [
            {dim: "2026-01-01", plan.metrics[0].id: 10},
            {dim: "2026-01-02", plan.metrics[0].id: 20},
        ]


class TestRepairScenarios(unittest.TestCase):
    """多提示词 + mock LLM 输出 → repair 收敛到预期。"""

    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.csv_events = list_distinct_csv_events(load_data_pool())
        cls.ctx = {"index": cls.index, "csv_events": cls.csv_events}

    def test_repair_scenarios_all_queries(self):
        for scenario in REPAIR_SCENARIOS:
            if scenario.mock_llm_payload is None and scenario.expect.scope_mode:
                for query in scenario.queries:
                    with self.subTest(scenario=scenario.id, query=query):
                        mode = infer_scope_mode_fallback(query)
                        self.assertEqual(mode, scenario.expect.scope_mode)
                continue
            if scenario.mock_llm_payload is None:
                continue
            for query in scenario.queries:
                with self.subTest(scenario=scenario.id, query=query):
                    payload = _apply_repair(
                        scenario, query, scenario.mock_llm_payload, self.ctx
                    )
                    plan = AnalysisPlan.model_validate(payload)
                    _assert_expectation(self, scenario.expect, payload=payload, plan=plan)


class TestChartAllowedMatrix(unittest.TestCase):
    """每种 analysis_type 的 default_chart 在其允许列表内。"""

    def test_default_charts_valid(self):
        for spec in ANALYSIS_CATALOG:
            allowed = set(spec["chart_types"])
            self.assertIn(spec["default_chart"], allowed, msg=spec["id"])

    def test_normalize_rejects_invalid_chart(self):
        plan = normalize_plan_for_analysis(
            build_plan_for_type("time_series", chart_type="funnel_chart"),
            query="趋势",
        )
        self.assertIn(plan.visualization.chart_type, get_allowed_chart_types("time_series"))


@unittest.skipUnless(get_deepseek_api_key(), "需要 DEEPSEEK_API_KEY")
class TestLlmAnalyzeScenarios(unittest.TestCase):
    """端到端：多提示词调用 /api/analyze，断言预期回复。"""

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

    def _analyze(self, query: str) -> tuple[dict, float]:
        t0 = time.perf_counter()
        r = self.client.post(
            "/api/analyze",
            json={"query": query, "analysis_mode": "auto", "locale": "zh"},
        )
        elapsed = time.perf_counter() - t0
        self.assertEqual(r.status_code, 200, msg=f"{query!r} -> {r.text[:400]}")
        return r.json(), elapsed

    def test_llm_scenarios_all_queries(self):
        for scenario in LLM_SCENARIOS:
            for query in scenario.queries:
                with self.subTest(scenario=scenario.id, query=query):
                    data, elapsed = self._analyze(query)
                    _assert_expectation(self, scenario.expect, response=data)
                    print(
                        f"  [{scenario.id}] {query[:30]!r}… "
                        f"mode={data.get('mode')} "
                        f"type={(data.get('plan') or {}).get('analysis_type')} "
                        f"elapsed={elapsed:.1f}s"
                    )


class TestScenarioRegistryCompleteness(unittest.TestCase):
    """场景注册表与 ANALYSIS_CATALOG 对齐检查。"""

    def test_llm_scenarios_touch_core_types(self):
        touched = {
            s.expect.analysis_type
            for s in LLM_SCENARIOS
            if s.expect.analysis_type
        }
        core = {
            "time_series",
            "usage_retention",
            "funnel",
            "event_comparison",
            "period_pattern",
            "summary_kpi",
        }
        self.assertTrue(core.issubset(touched | ANALYSIS_TYPE_IDS))

    def test_repair_scenarios_have_multiple_queries(self):
        for scenario in ALL_QUERY_SCENARIOS:
            self.assertGreaterEqual(
                len(scenario.queries),
                2,
                msg=f"{scenario.id} 应至少 2 种用户说法",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
