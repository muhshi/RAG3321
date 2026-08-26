"""
Unit test to verify table cleaning, multi-index header flattening,
and Indonesian BPS number conversion logic.
"""
import unittest
import pandas as pd
import numpy as np
from modules.extraction.table_cleaner import TableCleaner


class TestTableCleaner(unittest.TestCase):

    def test_flatten_multi_index_headers(self):
        # Multi-level BPS table header simulation
        raw_headers = [
            ["Kecamatan", "Jumlah Penduduk", "", "Luas Wilayah"],
            ["(1)", "(2)", "(3)", "(4)"],
            ["", "Laki-laki", "Perempuan", "km2"]
        ]
        flattened = TableCleaner.flatten_multi_index_headers(raw_headers)
        expected = [
            "Kecamatan",
            "Jumlah_Penduduk_Laki_laki",
            "Jumlah_Penduduk_Perempuan",
            "Luas_Wilayah_km2"
        ]
        self.assertEqual(flattened, expected)

    def test_indonesian_numeric_sanitization(self):
        # Dash to 0
        self.assertEqual(TableCleaner.sanitize_indonesian_numeric("-"), 0)
        self.assertEqual(TableCleaner.sanitize_indonesian_numeric("–"), 0)
        
        # Missing / NA
        self.assertIsNone(TableCleaner.sanitize_indonesian_numeric("..."))
        self.assertIsNone(TableCleaner.sanitize_indonesian_numeric(None))
        
        # Indonesian thousand & decimal separator
        self.assertEqual(TableCleaner.sanitize_indonesian_numeric("1.234,50"), 1234.5)
        self.assertEqual(TableCleaner.sanitize_indonesian_numeric("12.500"), 12500)
        self.assertEqual(TableCleaner.sanitize_indonesian_numeric("100 Jiwa"), 100)

    def test_clean_table_dataframe_with_ffill(self):
        # Raw table matrix with merged rows and missing sub-values
        raw_matrix = [
            ["Kecamatan", "Kategori Usia", "Jumlah"],
            ["Mranggen", "0-14 Tahun", "15.000"],
            ["", "15-64 Tahun", "35.000"],
            ["Sayung", "0-14 Tahun", "12.000"],
            ["", "15-64 Tahun", "-"]
        ]
        df = TableCleaner.clean_table_dataframe(raw_matrix, header_depth=1)
        
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 4)
        # Check forward fill on Kecamatan column
        self.assertEqual(df["Kecamatan"].tolist(), ["Mranggen", "Mranggen", "Sayung", "Sayung"])
        # Check numeric conversions
        self.assertEqual(df["Jumlah"].tolist(), [15000, 35000, 12000, 0])


if __name__ == "__main__":
    unittest.main()
