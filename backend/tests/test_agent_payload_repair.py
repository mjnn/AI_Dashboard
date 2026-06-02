"""Agent LLM payload 修复单元测试。"""

import unittest

from schemas.agent_plan import AgentContextBundle, AgentIntent, AgentRevisionPayload, AgentStory, DictionaryLookup
from services.agent_payload_repair import repair_visualizations_payload


class TestAgentPayloadRepair(unittest.TestCase):
    def setUp(self):
        self.context = AgentContextBundle(
            intent=AgentIntent(goal="Carlog 漏斗", intent_confidence="high"),
            dictionary=DictionaryLookup(
                matched_event="Carlog_进入",
                matched_module="Carlog",
                csv_event_filter=["carlog_entry", "carlog_record", "carlog_exit"],
                comparison_events=["Carlog_进入", "Carlog_主动录制", "Carlog_退出"],
            ),
            story=AgentStory(
                headline="Carlog 转化漏斗",
                narrative="观察从进入到退出的转化路径",
            ),
        )

    def test_repair_revision_shorthand_time_range(self):
        raw = {
            "revision_summary": "调整时间窗",
            "visualizations": [
                {
                    "panel_id": "primary",
                    "analysis_type": "funnel",
                    "data_requirements": {
                        "csv_event_filter": ["carlog_entry", "carlog_record", "carlog_exit"],
                        "comparison_events": {
                            "carlog_entry": "Carlog_进入",
                            "carlog_exit": "Carlog_退出",
                        },
                        "time_range": "last_30d",
                    },
                },
                {
                    "panel_id": "secondary",
                    "analysis_type": "event_comparison",
                    "data_requirements": {
                        "csv_event_filter": ["carlog_autocut"],
                        "time_range": "last_30d",
                    },
                },
            ],
        }
        repaired = repair_visualizations_payload(raw, self.context)
        payload = AgentRevisionPayload.model_validate(repaired)
        self.assertEqual(len(payload.visualizations), 2)
        self.assertEqual(payload.visualizations[0].chart_type, "funnel_chart")
        self.assertEqual(payload.visualizations[0].data_requirements.time_range.type, "last_n_days")
        self.assertEqual(payload.visualizations[0].data_requirements.time_range.value, 30)
        self.assertGreaterEqual(len(payload.visualizations[0].data_requirements.metrics), 1)

    def test_repair_invalid_metric_type_rate(self):
        raw = {
            "visualizations": [
                {
                    "panel_id": "primary",
                    "analysis_type": "event_comparison",
                    "data_requirements": {
                        "metrics": [
                            {"id": "pv", "name": "次数", "type": "count"},
                            {"id": "conv", "name": "转化率", "type": "rate"},
                        ],
                    },
                }
            ],
        }
        repaired = repair_visualizations_payload(raw, self.context)
        payload = AgentRevisionPayload.model_validate(repaired)
        metric_types = [
            metric.type for metric in payload.visualizations[0].data_requirements.metrics
        ]
        self.assertEqual(metric_types[1], "count")

    def test_repair_formula_components_nested_dict(self):
        raw = {
            "visualizations": [
                {
                    "panel_id": "primary",
                    "analysis_type": "time_series",
                    "data_requirements": {
                        "metrics": [
                            {
                                "id": "penetration",
                                "name": "渗透率",
                                "type": "formula",
                                "formula": "uv_vin / total_vehicles",
                                "formula_components": {
                                    "nunique(vin_code)": {
                                        "field": "vin_code",
                                        "vehicles": {"value": 1000},
                                    },
                                    "total_vehicles": {"value": 1000},
                                },
                            }
                        ],
                    },
                }
            ],
        }
        repaired = repair_visualizations_payload(raw, self.context)
        payload = AgentRevisionPayload.model_validate(repaired)
        components = payload.visualizations[0].data_requirements.metrics[0].formula_components
        self.assertIsInstance(components, list)
        self.assertGreaterEqual(len(components), 1)
        self.assertIn("uv_vin", components)

    def test_repair_filters_csv_event_filter_list_hoisted(self):
        raw = {
            "revision_summary": "修正 filters",
            "visualizations": [
                {
                    "panel_id": "primary",
                    "analysis_type": "event_comparison",
                    "data_requirements": {
                        "filters": {
                            "csv_event_filter": [
                                "hu_naviyawing",
                                "hu_naviforecastset_btnclick",
                            ]
                        },
                        "metrics": [{"id": "pv", "name": "次数", "type": "count"}],
                    },
                },
                {
                    "panel_id": "secondary",
                    "analysis_type": "time_series",
                    "data_requirements": {
                        "filters": {
                            "csv_event_filter": [
                                "hu_naviyawing",
                                "hu_naviparkbtnclick",
                            ]
                        },
                    },
                },
            ],
        }
        repaired = repair_visualizations_payload(raw, self.context)
        payload = AgentRevisionPayload.model_validate(repaired)
        self.assertEqual(
            payload.visualizations[0].data_requirements.csv_event_filter,
            ["hu_naviyawing", "hu_naviforecastset_btnclick"],
        )
        self.assertEqual(payload.visualizations[0].data_requirements.filters, {})
        self.assertNotIn(
            "csv_event_filter",
            payload.visualizations[1].data_requirements.filters,
        )


if __name__ == "__main__":
    unittest.main()
