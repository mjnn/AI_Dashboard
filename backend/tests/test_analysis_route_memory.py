"""分析路线记忆单元测试。"""

import unittest

from schemas.agent_plan import (
    AgentContextBundle,
    AgentIntent,
    AgentStory,
    DictionaryLookup,
)
from services.analysis_route_memory import (
    build_route_signature,
    clear_route_cache,
    lookup_route,
    remember_route,
    should_bypass_cache,
    skip_feasibility_on_cache_hit,
)


class TestAnalysisRouteMemory(unittest.TestCase):
    def setUp(self):
        clear_route_cache()
        self.context = AgentContextBundle(
            intent=AgentIntent(
                goal="Carlog 综合分析",
                intent_confidence="high",
                exploratory_mode=True,
                user_focus="综合分析",
            ),
            dictionary=DictionaryLookup(
                matched_event="Carlog_进入",
                matched_module="Carlog",
                csv_event_filter=["carlog_entry", "carlog_exit"],
                comparison_events=["Carlog_进入", "Carlog_退出"],
            ),
            story=AgentStory(
                headline="Carlog 概览",
                narrative="观察各子事件触发情况",
                takeaway="关注录制转化",
            ),
        )

    def tearDown(self):
        clear_route_cache()

    def test_signature_normalizes_comprehensive_carlog(self):
        sig_a = build_route_signature("综合分析 carlog")
        sig_b = build_route_signature("全面分析 Carlog 模块")
        self.assertEqual(sig_a, sig_b)
        self.assertIn("scope:comprehensive", sig_a)
        self.assertIn("mod:carlog", sig_a)

    def test_bypass_on_refresh_intent(self):
        self.assertTrue(should_bypass_cache("换个角度分析 carlog"))
        self.assertFalse(should_bypass_cache("综合分析 carlog"))

    def test_remember_and_lookup(self):
        from schemas.agent_plan import VisualizationProposal, DataRequirementSpec

        proposal = VisualizationProposal(
            panel_id="primary",
            analysis_type="event_comparison",
            chart_type="bar",
            title="对比",
            reasoning="多事件对比",
            data_requirements=DataRequirementSpec(
                csv_event_filter=["carlog_entry", "carlog_exit"],
                metrics=[{"id": "pv", "name": "次数", "type": "count"}],
            ),
        )
        remember_route(
            "综合分析 carlog",
            locale="zh",
            context=self.context,
            proposals=[proposal],
            converged=True,
        )
        hit = lookup_route("全面分析 carlog", locale="zh")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.context.dictionary.matched_event, "Carlog_进入")
        self.assertEqual(len(hit.proposals), 1)

    def test_skip_feasibility_default_enabled(self):
        self.assertTrue(skip_feasibility_on_cache_hit())


if __name__ == "__main__":
    unittest.main()
