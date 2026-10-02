import tempfile
import unittest
from pathlib import Path

from src.option_trade_chart import OptionTradeChart


class TestOptionTradeChart(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.quote_file = Path(self.temp_dir.name) / "quotes.csv"
        self.quote_file.write_text(
            "2026-10-01 09:30;100.0;100.0;OPT-A;2.0;2.2;delta=0.5\n"
            "2026-10-01 09:30;105.0;100.0;OPT-B;0.4;0.5;delta=0.3\n"
            "2026-10-01 09:35;100.0;101.0;OPT-A;1.4;1.5;delta=0.6\n"
            "2026-10-01 09:35;105.0;101.0;OPT-B;0.7;0.8;delta=0.4\n",
            encoding="utf-8",
        )
        self.chart = OptionTradeChart(self.quote_file)
        self.order = {
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": "1",
                    "instrument": {"symbol": "OPT-A"},
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": "1",
                    "instrument": {"symbol": "OPT-B"},
                },
            ]
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_calculates_spread_pnl_from_entry_time(self):
        history = self.chart.calculate_profit_loss(self.order, "2026-10-01 09:31")

        self.assertEqual(len(history), 2)
        self.assertAlmostEqual(history.iloc[0]["profit_loss"], -30.0)
        self.assertAlmostEqual(history.iloc[1]["profit_loss"], 70.0)

    def test_rejects_entry_without_prior_contract_quote(self):
        with self.assertRaisesRegex(ValueError, "No quote for OPT-A"):
            self.chart.calculate_profit_loss(self.order, "2026-10-01 09:00")


if __name__ == "__main__":
    unittest.main()