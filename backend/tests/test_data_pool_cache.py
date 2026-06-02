"""CSV 数据池进程内缓存单元测试。"""

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from services.csv_processor import (
    invalidate_data_pool_cache,
    load_data_pool,
)


class TestDataPoolCache(unittest.TestCase):
    def tearDown(self):
        invalidate_data_pool_cache()

    @patch("services.csv_processor._read_csv_with_encoding")
    @patch("config.list_csv_files")
    @patch("config.resolve_csv_data_dir")
    @patch("config.data_pool_cache_key")
    def test_load_data_pool_caches_by_mtime_key(
        self,
        mock_cache_key,
        mock_resolve_dir,
        mock_list_files,
        mock_read_csv,
    ):
        mock_cache_key.return_value = "pool-v1"
        mock_resolve_dir.return_value = Path("/data")
        mock_list_files.return_value = [{"filename": "a.csv"}]
        frame = pd.DataFrame({"event": ["e1"], "vin": ["v1"]})
        mock_read_csv.return_value = frame

        first = load_data_pool()
        second = load_data_pool()

        self.assertIs(first, second)
        mock_read_csv.assert_called_once()

    @patch("services.csv_processor._read_csv_with_encoding")
    @patch("config.list_csv_files")
    @patch("config.resolve_csv_data_dir")
    @patch("config.data_pool_cache_key")
    def test_invalidate_forces_reload(
        self,
        mock_cache_key,
        mock_resolve_dir,
        mock_list_files,
        mock_read_csv,
    ):
        mock_cache_key.return_value = "pool-v1"
        mock_resolve_dir.return_value = Path("/data")
        mock_list_files.return_value = [{"filename": "a.csv"}]
        frame = pd.DataFrame({"event": ["e1"]})
        mock_read_csv.return_value = frame

        load_data_pool()
        invalidate_data_pool_cache()
        load_data_pool(force_reload=True)

        self.assertEqual(mock_read_csv.call_count, 2)


if __name__ == "__main__":
    unittest.main()
