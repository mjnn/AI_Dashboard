"""事件展示名单元测试。"""

import unittest

from services.dict_preprocessor import DictPreprocessor
from config import EVENTS_DICT_PATH
from services.event_display import display_name_for_event_ref


class TestEventDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DictPreprocessor(EVENTS_DICT_PATH).index

    def test_csv_label_maps_to_chinese_name(self):
        name = display_name_for_event_ref(
            "Hu_naviEnd_BtnClick",
            self.index,
            locale="zh",
        )
        self.assertEqual(name, "结束导航")

    def test_long_canonical_shortened(self):
        long_name = (
            "用户发起导航（包括算路进入导航、poi详情快速导航、生态域发起导航、"
            "消息中心发起导航、SOA触发导航、日程日历发起导航等所有由非导航进入导航的场景）"
        )
        short = display_name_for_event_ref(long_name, self.index, locale="zh")
        self.assertLess(len(short), len(long_name))
        self.assertNotIn("（", short)
        self.assertIn("导航", short)

    def test_heuristic_short_alias(self):
        from services.event_display import heuristic_short_alias

        name = heuristic_short_alias(
            "用户发起导航（包括算路进入导航、poi详情快速导航）"
        )
        self.assertEqual(name, "发起导航")


if __name__ == "__main__":
    unittest.main()
