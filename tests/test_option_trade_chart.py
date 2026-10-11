import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_plots_combined_pnl_for_multiple_orders(self):
        single_trade_pnl = self.chart.calculate_profit_loss(
            self.order, "2026-10-01 09:31"
        )["profit_loss"]
        with patch("matplotlib.pyplot.show"):
            figure, axis = self.chart.plot_trade(
                [self.order, self.order], "2026-10-01 09:31"
            )

        plotted_pnl = axis.lines[0].get_ydata()
        for actual, single_pnl in zip(plotted_pnl, single_trade_pnl):
            self.assertAlmostEqual(actual, single_pnl * 2)
        self.assertEqual(axis.texts[0].get_text(), "Net entry credit: $330.00")

        import matplotlib.pyplot as plt

        plt.close(figure)

    def test_plots_trades_with_different_entry_times(self):
        first_trade = self.chart.calculate_profit_loss(
            self.order, "2026-10-01 09:31"
        )["profit_loss"]
        second_trade = self.chart.calculate_profit_loss(
            self.order, "2026-10-01 09:35"
        )["profit_loss"]

        with patch("matplotlib.pyplot.show"):
            figure, axis = self.chart.plot_trade(
                [self.order, self.order],
                ["2026-10-01 09:31", "2026-10-01 09:35"],
            )

        plotted_pnl = axis.lines[0].get_ydata()
        self.assertAlmostEqual(plotted_pnl[0], first_trade.iloc[0])
        self.assertAlmostEqual(
            plotted_pnl[-1], first_trade.iloc[-1] + second_trade.iloc[-1]
        )

        import matplotlib.pyplot as plt

        plt.close(figure)

    def test_rejects_entry_time_sequence_with_wrong_length(self):
        with patch("matplotlib.pyplot.show"):
            with self.assertRaisesRegex(ValueError, "one timestamp per order"):
                self.chart.plot_trade(
                    [self.order, self.order], ["2026-10-01 09:31"]
                )


if __name__ == "__main__":
    unittest.main()