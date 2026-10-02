import unittest
from unittest.mock import Mock, patch

from src.schwab import SchwabClient


class TestCompareMultiLegOptionOrders(unittest.TestCase):
    def setUp(self):
        self.buy_order = {
            "price": "1.20",
            "quantity": "2",
            "orderLegCollection": [
                {
                    "instruction": "BUY_TO_OPEN",
                    "quantity": "2",
                    "instrument": {"symbol": "OPT-A"},
                },
                {
                    "instruction": "SELL_TO_OPEN",
                    "quantity": "2",
                    "instrument": {"symbol": "OPT-B"},
                },
            ],
        }
        self.sell_order = {
            "price": "1.75",
            "quantity": "2",
            "orderLegCollection": [
                {
                    "instruction": "SELL_TO_CLOSE",
                    "quantity": "2",
                    "instrument": {"symbol": "OPT-A"},
                },
                {
                    "instruction": "BUY_TO_CLOSE",
                    "quantity": "2",
                    "instrument": {"symbol": "OPT-B"},
                },
            ],
        }

    def test_calculates_profit_for_matching_reversed_legs(self):
        result = SchwabClient.compare_multi_leg_option_orders(self.buy_order, self.sell_order)

        self.assertEqual(result["profit_per_share"], 0.55)
        self.assertEqual(result["profit_loss"], 110.0)
        self.assertTrue(result["is_profitable"])

    def test_rejects_different_contracts(self):
        self.sell_order["orderLegCollection"][0]["instrument"]["symbol"] = "OPT-C"

        with self.assertRaisesRegex(ValueError, "same option contracts"):
            SchwabClient.compare_multi_leg_option_orders(self.buy_order, self.sell_order)

    def test_declining_confirmation_does_not_submit_order(self):
        client = object.__new__(SchwabClient)
        client._client = Mock()
        client._account_hash = "test-account"
        client._order_manager = Mock()

        with patch("builtins.input", return_value="no"):
            result = client.place_order("ABC", 5, action="buy", price=10.0)

        self.assertEqual(result, (None, None))
        client._client.place_order.assert_not_called()


if __name__ == "__main__":
    unittest.main()