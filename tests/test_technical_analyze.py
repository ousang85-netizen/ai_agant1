import unittest

import pandas as pd

from src.technical_analyze import TechnicalAnalyzer


class TestCheckRisingPrice(unittest.TestCase):
    def setUp(self):
        self.analyzer = TechnicalAnalyzer.__new__(TechnicalAnalyzer)

    def test_reports_recovery_from_previous_low(self):
        history = pd.DataFrame(
            {"Low": [98, 90, 94, 105], "Close": [100, 92, 96, 108]},
            index=pd.date_range("2026-01-01", periods=4),
        )

        result = self.analyzer.check_rising_price(history, lookback=2)

        self.assertTrue(result["is_rising"])
        self.assertEqual(result["low_price"], 94.0)
        self.assertEqual(result["low_date"], history.index[2])
        self.assertEqual(result["current_price"], 108.0)
        self.assertEqual(result["price_change"], 14.0)
        self.assertAlmostEqual(result["percent_change"], 14.893617)

    def test_reports_no_rise_when_price_falls(self):
        history = pd.DataFrame({"Low": [100, 105, 103], "Close": [101, 106, 102]})

        self.assertFalse(self.analyzer.check_rising_price(history, lookback=1)["is_rising"])

    def test_rejects_insufficient_history(self):
        with self.assertRaises(ValueError):
            self.analyzer.check_rising_price(pd.DataFrame({"Close": [100]}), lookback=1)


if __name__ == "__main__":
    unittest.main()