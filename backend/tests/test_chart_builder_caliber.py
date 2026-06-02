"""图表口径详情单元测试。"""

import unittest

from schemas.analysis import StatisticalCaliber
from services.analysis_registry import ANALYSIS_TYPE_IDS
from services.panel_caliber import build_panel_caliber_detail
from tests.fixtures.plan_factory import build_plan_for_type


class TestPanelCaliberDetail(unittest.TestCase):
    def test_funnel_includes_steps_and_formulas(self):
        plan = build_plan_for_type("funnel")
        detail = build_panel_caliber_detail(plan, events_index=None, locale="zh")
        self.assertGreaterEqual(len(detail.events), 2)
        joined = " ".join(detail.formulas)
        self.assertIn("到达车辆数", joined)
        self.assertIn("转化率", joined)
        self.assertTrue(any("漏斗" in line for line in detail.chart_layout))

    def test_time_series_single_event(self):
        plan = build_plan_for_type("time_series")
        detail = build_panel_caliber_detail(plan, events_index=None, locale="zh")
        self.assertEqual(len(detail.events), 1)
        joined = " ".join(detail.formulas)
        self.assertNotIn("COUNT", joined)
        self.assertTrue(any("触发" in item or "记录" in item for item in detail.formulas))
        layout = " ".join(detail.chart_layout)
        self.assertIn("横轴", layout)
        self.assertIn("纵轴", layout)

    def test_penetration_formula_is_natural_language(self):
        plan = build_plan_for_type("penetration")
        detail = build_panel_caliber_detail(plan, events_index=None, locale="zh")
        joined = " ".join(detail.formulas)
        self.assertIn("渗透率", joined)
        self.assertIn("独立车辆数", joined)
        self.assertNotIn("uv / pv", joined)

    def test_new_vs_returning_explains_grouping(self):
        plan = build_plan_for_type("new_vs_returning")
        plan = plan.model_copy(
            update={
                "statistical_caliber": StatisticalCaliber(
                    dedup_method="按VIN去重",
                    time_granularity="daily",
                    description="探索性分析：新老用户（Carlog_进入）",
                ),
            },
        )
        detail = build_panel_caliber_detail(plan, events_index=None, locale="zh")
        self.assertIn("首次", detail.description)
        self.assertGreaterEqual(len(detail.grouping_rules), 2)
        joined_rules = " ".join(detail.grouping_rules)
        self.assertIn("新用户", joined_rules)
        self.assertIn("老用户", joined_rules)
        self.assertIn("用户类型", " ".join(detail.formulas))
        layout = " ".join(detail.chart_layout)
        self.assertIn("新用户", layout)

    def test_all_analysis_types_have_chart_layout(self):
        for analysis_type in sorted(ANALYSIS_TYPE_IDS):
            with self.subTest(analysis_type=analysis_type):
                plan = build_plan_for_type(analysis_type)
                detail = build_panel_caliber_detail(plan, events_index=None, locale="zh")
                self.assertGreater(
                    len(detail.chart_layout),
                    0,
                    f"{analysis_type} 缺少 chart_layout",
                )
                self.assertGreater(
                    len(detail.formulas),
                    0,
                    f"{analysis_type} 缺少 formulas",
                )
                self.assertTrue(
                    detail.description.strip(),
                    f"{analysis_type} 缺少 description",
                )


if __name__ == "__main__":
    unittest.main()
