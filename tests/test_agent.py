import unittest
from unittest.mock import patch

import pandas as pd

from src.agent import TradingAgent
from src.ticker_scanner import collect_high_volume_close_tickers


class TestTradingAgent(unittest.TestCase):
    @patch("src.agent.collect_all_exchange_tickers")
    def test_run_does_not_raise(self, mock_collect):
        mock_collect.return_value = {"NYSE": ["AAPL"], "NASDAQ": ["MSFT"]}
        agent = TradingAgent()
        try:
            agent.run()
        except Exception as e:
            self.fail(f"agent.run() raised an exception: {e}")

    @patch("src.ticker_scanner.Overview.screener_view")
    def test_high_volume_close_filter(self, mock_screener_view):
        df = pd.DataFrame({"Ticker": ["AAPL", "PENNY"], "Price": [10.0, 6.0], "Volume": [2000000.0, 1000000.0]})
        mock_screener_view.return_value = df
        found = collect_high_volume_close_tickers("NASDAQ", min_volume=1500000, min_close=5.0)
        self.assertEqual(found, ["AAPL"])


if __name__ == "__main__":
    unittest.main()
