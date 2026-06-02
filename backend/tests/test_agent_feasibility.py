"""Agent 数据可行性校验单元测试（无 LLM）。"""

import unittest

from schemas.agent_plan import (
    AgentContextBundle,
    AgentIntent,
    AgentStory,
    DataRequirementSpec,
    DictionaryLookup,
    VisualizationProposal,
)
from schemas.analysis import MetricDef, TimeRange
from services.csv_processor import load_data_pool
from services.data_feasibility import check_data_feasibility
from services.data_profiler import list_distinct_csv_events
from services.dict_preprocessor import DictPreprocessor
from config import EVENTS_DICT_PATH


class TestDataFeasibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_data_pool()
        cls.columns = list(cls.df.columns)
        cls.csv_events = list_distinct_csv_events(cls.df)
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index
        cls.context = AgentContextBundle(
            intent=AgentIntent(
                goal="Carlog 转化漏斗",
                intent_confidence="high",
                user_focus="漏斗",
            ),
            dictionary=DictionaryLookup(
                matched_event="Carlog_进入",
                matched_module="Carlog",
                match_confidence="high",
                csv_event_filter=[
                    "carlog_entry",
                    "carlog_record",
                    "carlog_exit",
                ],
                comparison_events=["Carlog_进入", "Carlog_主动录制", "Carlog_退出"],
            ),
            story=AgentStory(
                headline="Carlog 漏斗",
                narrative="观察从进入到退出的转化",
            ),
        )

    def test_funnel_proposal_feasible(self):
        proposal = VisualizationProposal(
            panel_id="primary",
            analysis_type="funnel",
            chart_type="funnel_chart",
            layout="single",
            title="Carlog 漏斗",
            reasoning="转化漏斗",
            data_requirements=DataRequirementSpec(
                csv_event_filter=["carlog_entry", "carlog_record", "carlog_exit"],
                comparison_events=["Carlog_进入", "Carlog_主动录制", "Carlog_退出"],
                dimension="漏斗步骤",
                metrics=[
                    MetricDef(id="user_count", name="到达车辆数", type="count"),
                    MetricDef(id="conversion_rate", name="步间转化率(%)", type="count"),
                ],
                time_range=TimeRange(type="last_n_days", value=30),
            ),
        )
        result = check_data_feasibility(
            proposal,
            self.context,
            df=self.df,
            columns=self.columns,
            csv_event_names=self.csv_events,
            events_index=self.index,
            query="看看carlog漏斗",
        )
        self.assertTrue(result.ready, msg=result.issues)
        self.assertGreater(result.preview_rows, 0)


if __name__ == "__main__":
    unittest.main()
