import unittest

import pandas as pd

from src.ema_duration import EmaDuration


class TestEmaDuration(unittest.TestCase):
    def test_counts_only_the_current_streak(self):
        closes = pd.Series([10, 9, 8, 8, 10, 11, 12])
        self.assertEqual(EmaDuration(period=3).count_above(closes), 3)

    def test_returns_zero_when_latest_close_is_not_above_ema(self):
        closes = pd.Series([10, 11, 12, 8])
        self.assertEqual(EmaDuration(period=3).count_above(closes), 0)

    def test_rejects_invalid_period(self):
        with self.assertRaises(ValueError):
            EmaDuration(period=0)


if __name__ == "__main__":
    unittest.main()