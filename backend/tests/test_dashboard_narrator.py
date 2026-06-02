"""看板叙事兜底文案单元测试。"""

import unittest

from schemas.analysis import (
    AnalysisPanel,
    AnalysisPlan,
    ChartConfig,
    ExecutionSummary,
    MetricDef,
    StatisticalCaliber,
    TimeRange,
    VisualizationDef,
)
from services.dashboard_narrator import (
    _fallback_presentation,
    _panel_fallback_subtitle,
)
from services.panel_caliber import build_panel_caliber_detail


def _chart_config(**updates) -> ChartConfig:
    plan = _seed_plan()
    detail = build_panel_caliber_detail(plan, events_index=None, locale="zh")
    base = ChartConfig(
        chart_type="line",
        title="Carlog_进入 · 日趋势",
        x_axis_key="date",
        y_axis_keys=["pv"],
        series=[{"key": "pv", "name": "触发次数", "type": "line"}],
        data=[
            {"date": "2025-01-01", "pv": 10},
            {"date": "2025-01-02", "pv": 20},
        ],
        calibers=[detail.description],
        caliber_detail=detail,
    )
    return base.model_copy(update=updates)


def _seed_plan(**updates) -> AnalysisPlan:
    base = AnalysisPlan(
        analysis_type="time_series",
        matched_event="Carlog_进入",
        matched_module="Carlog",
        match_confidence="high",
        metrics=[MetricDef(id="pv", name="触发次数", type="count")],
        visualization=VisualizationDef(
            chart_type="line",
            layout="single",
            reasoning="Carlog_进入 单事件时间趋势",
        ),
        dimension="date",
        filters={},
        time_range=TimeRange(type="last_n_days", value=30),
        statistical_caliber=StatisticalCaliber(
            dedup_method="按VIN去重",
            time_granularity="daily",
            description="通过分析Carlog功能从进入、主动录制到编辑的三步漏斗，发现用户进入功能后主动录制转化率较高。",
        ),
    )
    return base.model_copy(update=updates)


def _panel(**updates) -> AnalysisPanel:
    plan = _seed_plan()
    chart = _chart_config()
    base = AnalysisPanel(
        panel_id="event-0-Carlog_进入",
        analysis_type="time_series",
        name="Carlog_进入 · 日趋势",
        layout="half",
        plan=plan,
        execution=ExecutionSummary(
            status="success",
            unavailable_dimensions=[],
            total_rows=100,
            filtered_rows=50,
            execution_time_ms=1,
        ),
        chart_config=chart,
    )
    return base.model_copy(update=updates)


class TestDashboardNarrator(unittest.TestCase):
    def test_fallback_subtitle_uses_panel_context_not_caliber(self):
        subtitle = _panel_fallback_subtitle(_panel())
        self.assertNotIn("三步漏斗", subtitle)
        self.assertIn("Carlog_进入", subtitle)

    def test_fallback_presentation_subtitles_differ_by_analysis_type(self):
        funnel_panel = _panel(
            panel_id="funnel-funnel-0",
            analysis_type="funnel",
            plan=_seed_plan(
                analysis_type="funnel",
                visualization=VisualizationDef(
                    chart_type="funnel_chart",
                    layout="single",
                    reasoning="相关事件转化漏斗",
                ),
            ),
            chart_config=_chart_config(
                chart_type="funnel_chart",
                title="Carlog 漏斗",
                x_axis_key="step",
                y_axis_keys=["user_count"],
                series=[{"key": "user_count", "name": "到达车辆数", "type": "funnel"}],
                data=[{"step": "进入", "user_count": 100}],
            ),
        )
        trend_panel = _panel()
        presentation = _fallback_presentation(
            [funnel_panel, trend_panel],
            _seed_plan(analysis_type="funnel"),
        )
        subtitles = {item.subtitle for item in presentation.panels}
        self.assertEqual(len(subtitles), 2)
        self.assertTrue(any("漏斗" in text for text in subtitles))
        self.assertTrue(any("日触发" in text or "走势" in text for text in subtitles))


if __name__ == "__main__":
    unittest.main()
