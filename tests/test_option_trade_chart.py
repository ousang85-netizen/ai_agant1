import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import call
from unittest.mock import patch

from src.option_trade_chart import OptionTradeChart, main


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

    def test_plots_trade_with_datetime_entry_time(self):
        with patch("matplotlib.pyplot.show"):
            figure, axis = self.chart.plot_trade(
                self.order, datetime(2026, 10, 1, 9, 31)
            )

        self.assertEqual(len(axis.lines), 2)
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

    def test_plot_command_builds_put_spread_from_date_quote_file(self):
        data_dir = Path(self.temp_dir.name)
        (data_dir / "spx_quote_20261016.csv").write_text(
            "2026-10-16 09:30;7750;7770;SPXW  261016P07760000;1.0;1.2;delta=-0.5\n",
            encoding="utf-8",
        )

        with patch.object(OptionTradeChart, "plot_trade", return_value="plotted") as plot:
            result = OptionTradeChart.plot_command(
                "buy spread at 7760", "2026-10-16", "09:30", data_dir
            )

        self.assertEqual(result, "plotted")
        order, entry_time = plot.call_args.args
        self.assertEqual(entry_time.isoformat(sep=" "), "2026-10-16 09:30:00")
        self.assertEqual(
            order["orderLegCollection"],
            [
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": "1",
                    "instrument": {
                        "symbol": "SPXW  261016P07760000",
                        "assetType": "OPTION",
                    },
                },
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": "1",
                    "instrument": {
                        "symbol": "SPXW  261016P07750000",
                        "assetType": "OPTION",
                    },
                },
            ],
        )

    def test_plot_command_builds_call_fly_and_rejects_unknown_command(self):
        data_dir = Path(self.temp_dir.name)
        (data_dir / "spx_quote_20261016.csv").write_text(
            "2026-10-16 09:30;7750;7750;SPXW  261016C07750000;1.0;1.2;delta=0.5\n",
            encoding="utf-8",
        )

        with patch.object(OptionTradeChart, "plot_trade", return_value="plotted") as plot:
            OptionTradeChart.plot_command(
                "BUY FLY AT 7760",
                date(2026, 10, 16),
                datetime(2026, 10, 16, 9, 30),
                data_dir,
            )

        order = plot.call_args.args[0]
        self.assertEqual(
            [
                (leg["instruction"], leg["quantity"], leg["instrument"]["symbol"])
                for leg in order["orderLegCollection"]
            ],
            [
                ("BUY_TO_OPEN", "1", "SPXW  261016C07750000"),
                ("SELL_TO_OPEN", "2", "SPXW  261016C07760000"),
                ("BUY_TO_OPEN", "1", "SPXW  261016C07770000"),
            ],
        )
        with self.assertRaisesRegex(ValueError, "command must be"):
            OptionTradeChart.plot_command(
                "buy condor at 7760", "2026-10-16", "09:30", data_dir
            )

    def test_main_plots_each_trade_command_until_quit(self):
        user_inputs = [
            "date",
            "2026-10-16",
            "buy spread at 7760",
            "09:30",
            "buy fly at 7770",
            "09:45",
            "quit",
        ]
        with patch("builtins.input", side_effect=user_inputs), patch.object(
            OptionTradeChart, "plot_command"
        ) as plot_command:
            main()

        self.assertEqual(
            plot_command.call_args_list,
            [
                call("buy spread at 7760", date(2026, 10, 16).isoformat(), "09:30"),
                call("buy fly at 7770", date(2026, 10, 16).isoformat(), "09:45"),
            ],
        )


if __name__ == "__main__":
    unittest.main()