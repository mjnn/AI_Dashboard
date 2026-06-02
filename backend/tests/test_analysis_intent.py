"""analysis_intent 与 expand_event_scope 闸门测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config import EVENTS_DICT_PATH  # noqa: E402
from services.analysis_intent import (  # noqa: E402
    effective_scope_mode,
    should_run_multi_event_dashboard,
    should_widen_event_scope,
)
from services.data_profiler import list_distinct_csv_events  # noqa: E402
from services.dict_preprocessor import DictPreprocessor  # noqa: E402
from services.csv_processor import load_data_pool  # noqa: E402
from services.event_scope import expand_event_scope  # noqa: E402
from schemas.analysis import AnalysisPlan, MetricDef, StatisticalCaliber, TimeRange, VisualizationDef  # noqa: E402


def _minimal_plan(**kwargs) -> AnalysisPlan:
    base = dict(
        matched_event="Carlog_进入",
        matched_module="Carlog",
        match_confidence="high",
        metrics=[MetricDef(id="pv", name="触发次数", type="count")],
        visualization=VisualizationDef(
            chart_type="bar", layout="single", reasoning="test"
        ),
        dimension="date",
        filters={},
        time_range=TimeRange(type="last_n_days", value=30),
        statistical_caliber=StatisticalCaliber(
            dedup_method="按VIN去重",
            time_granularity="daily",
            description="test",
        ),
    )
    base.update(kwargs)
    return AnalysisPlan.model_validate(base)


class TestAnalysisIntent(unittest.TestCase):
    def test_single_event_default_no_widen(self):
        plan = _minimal_plan(scope_mode="single_event")
        mode = effective_scope_mode(query="进入carlog1次和2次的用户数", plan=plan)
        self.assertEqual(mode, "single_event")
        self.assertFalse(
            should_widen_event_scope(mode, "进入carlog1次和2次的用户数")
        )
        self.assertFalse(
            should_run_multi_event_dashboard(mode, "进入carlog1次和2次的用户数")
        )

    def test_comprehensive_query_widens(self):
        plan = _minimal_plan(scope_mode="single_event")
        q = "综合分析一下carlog"
        self.assertTrue(should_widen_event_scope("single_event", q))
        self.assertTrue(should_run_multi_event_dashboard("single_event", q))


class TestExpandEventScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.csv_events = list_distinct_csv_events(load_data_pool())

    def test_single_event_scope_only_entry_labels(self):
        scope, canonicals = expand_event_scope(
            scope_mode="single_event",
            matched_event="Carlog_进入",
            matched_module="Carlog",
            csv_event_filter=["carlog_entry", "carlog_record", "carlog_exit"],
            query="进入carlog1次和2次的用户数",
            events_index=self.index,
            csv_event_names=self.csv_events,
        )
        self.assertEqual(scope, {"carlog_entry"})
        self.assertEqual(canonicals, ["Carlog_进入"])

    def test_module_scope_broader_than_single(self):
        single, _ = expand_event_scope(
            scope_mode="single_event",
            matched_event="Carlog_进入",
            matched_module="Carlog",
            csv_event_filter=None,
            query="分析carlog",
            events_index=self.index,
            csv_event_names=self.csv_events,
        )
        module, _ = expand_event_scope(
            scope_mode="module",
            matched_event="Carlog_进入",
            matched_module="Carlog",
            csv_event_filter=None,
            query="分析carlog",
            events_index=self.index,
            csv_event_names=self.csv_events,
        )
        self.assertLess(len(single), len(module))


if __name__ == "__main__":
    unittest.main()
