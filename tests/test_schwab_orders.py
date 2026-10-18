import unittest
from datetime import date, datetime
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from src.schwab import NEW_YORK_TIMEZONE, SPX_SYMBOL, SchwabClient


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


class TestPlaceSpX0DteSingleLegOrder(unittest.TestCase):
    def setUp(self):
        self.client = object.__new__(SchwabClient)
        self.client._client = Mock()
        self.client._account_hash = "test-account"
        self.client._orders = []
        self.client._order_manager = Mock()

    def test_selects_qualifying_call_nearest_to_underlying_and_submits_buy(self):
        market_date = datetime.now(NEW_YORK_TIMEZONE).date()
        today = market_date.isoformat()
        expiration_code = market_date.strftime("%y%m%d")
        chain_response = Mock(status_code=200)
        chain_response.json.return_value = {
            "callExpDateMap": {
                f"{today}:0": {
                    "5000.0": [
                        {"symbol": f"SPXW  {expiration_code}C05000000", "ask": 1.50}
                    ],
                    "5010.0": [
                        {"symbol": f"SPXW  {expiration_code}C05010000", "ask": 1.25}
                    ],
                    "5020.0": [
                        {"symbol": f"SPXW  {expiration_code}C05020000", "ask": 1.10}
                    ],
                }
            }
        }
        submitted_response = Mock(status_code=201)
        submitted_response.headers = {"location": "/orders/order-123"}
        self.client._client.option_chains.return_value = chain_response
        self.client._client.place_order.return_value = submitted_response

        with patch.object(
            self.client,
            "get_quote",
            return_value={SPX_SYMBOL: {"quote": {"lastPrice": 5008}}},
        ), patch.object(self.client, "_confirm_order", return_value=True):
            response, order_id = self.client.place_spx_0dte_single_leg_order(
                "buy", "call"
            )

        order = self.client._client.place_order.call_args.args[1]
        self.assertIs(response, submitted_response)
        self.assertEqual(order_id, "order-123")
        self.assertEqual(order["price"], "1.25")
        self.assertEqual(order["orderType"], "LIMIT")
        self.assertEqual(order["orderLegCollection"][0]["quantity"], "1")
        self.assertEqual(
            order["orderLegCollection"][0]["instrument"]["symbol"],
            f"SPXW  {expiration_code}C05010000",
        )
        self.assertEqual(self.client._orders, ["order-123"])

    def test_rejects_non_call_or_put_type(self):
        with self.assertRaisesRegex(ValueError, "must be 'CALL' or 'PUT'"):
            self.client.place_spx_0dte_single_leg_order("BUY", "SPREAD")

        self.client._client.option_chains.assert_not_called()

    def test_rejects_sell_action_before_fetching_quotes(self):
        with patch.object(self.client, "get_quote") as get_quote:
            with self.assertRaisesRegex(ValueError, "Only 'BUY' action is supported"):
                self.client.place_spx_0dte_single_leg_order("sell", "call")

        get_quote.assert_not_called()
        self.client._client.option_chains.assert_not_called()

    def test_rejects_other_actions_before_fetching_quotes(self):
        with self.assertRaisesRegex(ValueError, "Only 'BUY' action is supported"):
            self.client.place_spx_0dte_single_leg_order("HOLD", "CALL")

        self.client._client.option_chains.assert_not_called()

    def test_uses_caller_supplied_market_date_for_option_chain(self):
        market_date = date(2026, 10, 16)
        chain_response = Mock(status_code=200)
        chain_response.json.return_value = {
            "callExpDateMap": {
                "2026-10-16:0": {
                    "5000.0": [
                        {
                            "symbol": "SPXW  261016C05000000",
                            "ask": 1.50,
                        }
                    ]
                }
            }
        }
        self.client._client.option_chains.return_value = chain_response

        with patch.object(
            self.client,
            "get_quote",
            return_value={SPX_SYMBOL: {"quote": {"lastPrice": 5000}}},
        ), patch.object(self.client, "_confirm_order", return_value=False):
            self.client.place_spx_0dte_single_leg_order(
                "buy", "call", market_date=market_date
            )

        self.client._client.option_chains.assert_called_once()
        chain_kwargs = self.client._client.option_chains.call_args.kwargs
        self.assertEqual(chain_kwargs["symbol"], SPX_SYMBOL)
        self.assertEqual(chain_kwargs["contractType"], "CALL")
        self.assertEqual(chain_kwargs["fromDate"], "2026-10-16")
        self.assertEqual(chain_kwargs["toDate"], "2026-10-16")
        self.assertNotIn("daysToExpiration", chain_kwargs)
        self.client._client.place_order.assert_not_called()

    def test_rejects_invalid_market_date(self):
        with patch.object(self.client, "get_quote") as get_quote:
            with self.assertRaisesRegex(TypeError, "market_date must be"):
                self.client.place_spx_0dte_single_leg_order(
                    "buy", "call", market_date="2026-10-16"
                )

        get_quote.assert_not_called()
        self.client._client.option_chains.assert_not_called()

    def test_fails_without_contract_in_price_range(self):
        market_date = datetime.now(NEW_YORK_TIMEZONE).date()
        today = market_date.isoformat()
        expiration_code = market_date.strftime("%y%m%d")
        chain_response = Mock(status_code=200)
        chain_response.json.return_value = {
            "putExpDateMap": {
                f"{today}:0": {
                    "5000.0": [
                        {"symbol": f"SPXW  {expiration_code}P05000000", "ask": 1.19}
                    ]
                }
            }
        }
        self.client._client.option_chains.return_value = chain_response
        with patch.object(
            self.client,
            "get_quote",
            return_value={SPX_SYMBOL: {"quote": {"lastPrice": 5000}}},
        ):
            with self.assertRaisesRegex(ValueError, "ask between \\$1.20 and \\$1.80"):
                self.client.place_spx_0dte_single_leg_order("buy", "put")

        self.client._client.place_order.assert_not_called()


class TestFindSpXCreditSpread(unittest.TestCase):
    def setUp(self):
        self.client = object.__new__(SchwabClient)
        self.client._client = Mock()

    @staticmethod
    def contract(option_type, strike, delta, bid, ask):
        option_code = "C" if option_type == "CALL" else "P"
        strike_code = f"{int(strike * 1000):08d}"
        return {
            "symbol": f"SPXW  {datetime.now(NEW_YORK_TIMEZONE):%y%m%d}{option_code}{strike_code}",
            "delta": delta,
            "bid": bid,
            "ask": ask,
        }

    def test_finds_call_spread_with_delta_closest_below_point_two(self):
        market_date = datetime.now(NEW_YORK_TIMEZONE).date().isoformat()
        self.client._client.option_chains.return_value = Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "callExpDateMap": {
                        f"{market_date}:0": {
                            "4990.0": [
                                self.contract("CALL", 4990, 0.12, 5.50, 5.70)
                            ],
                            "5000.0": [
                                self.contract("CALL", 5000, 0.19, 2.50, 2.70)
                            ],
                            "5010.0": [
                                self.contract("CALL", 5010, 0.05, 1.00, 1.20)
                            ],
                        }
                    }
                }
            ),
        )

        result = self.client.find_spx_credit_spread("call")

        self.assertEqual(result["sell_strike"], 5000)
        self.assertAlmostEqual(result["sell_delta"], 0.19)
        self.assertEqual(result["buy_strike"], 5010)
        self.assertAlmostEqual(result["spread_mid"], 1.5)

    def test_finds_put_spread_with_delta_closest_above_minus_point_two(self):
        market_date = datetime.now(NEW_YORK_TIMEZONE).date().isoformat()
        self.client._client.option_chains.return_value = Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "putExpDateMap": {
                        f"{market_date}:0": {
                            "5000.0": [
                                self.contract("PUT", 5000, -0.12, 2.50, 2.70)
                            ],
                            "4990.0": [
                                self.contract("PUT", 4990, -0.19, 2.20, 2.40)
                            ],
                            "4980.0": [
                                self.contract("PUT", 4980, -0.05, 0.70, 0.90)
                            ],
                        }
                    }
                }
            ),
        )

        result = self.client.find_spx_credit_spread("put")

        self.assertEqual(result["sell_strike"], 4990)
        self.assertAlmostEqual(result["sell_delta"], -0.19)
        self.assertEqual(result["buy_strike"], 4980)
        self.assertAlmostEqual(result["spread_mid"], 1.5)

    def test_rejects_invalid_contract_type(self):
        with self.assertRaisesRegex(ValueError, "must be 'CALL' or 'PUT'"):
            self.client.find_spx_credit_spread("FLY")

        self.client._client.option_chains.assert_not_called()

    def test_past_date_reads_requested_time_from_data_quote_file(self):
        market_date = date(2026, 10, 16)
        expiration_code = market_date.strftime("%y%m%d")
        chain = {
            "5000.0": [
                {
                    "symbol": f"SPXW  {expiration_code}C05000000",
                    "delta": 0.19,
                    "bid": 2.50,
                    "ask": 2.70,
                }
            ],
            "5010.0": [
                {
                    "symbol": f"SPXW  {expiration_code}C05010000",
                    "delta": 0.10,
                    "bid": 1.00,
                    "ask": 1.20,
                }
            ],
        }

        with patch.object(
            self.client, "_load_spx_quote_snapshot", return_value=chain
        ) as load_snapshot:
            result = self.client.find_spx_credit_spread(
                "CALL", date=market_date, time="09:30"
            )

        quote_file = load_snapshot.call_args.args[0]
        self.assertEqual(
            quote_file,
            Path(__file__).resolve().parent.parent
            / "data"
            / "spx_quote_20261016.csv",
        )
        self.assertEqual(load_snapshot.call_args.args[1:], (
            market_date,
            datetime.strptime("09:30", "%H:%M").time(),
            "CALL",
        ))
        self.assertEqual(result["sell_strike"], 5000)

    def test_past_date_requires_quote_time(self):
        with self.assertRaisesRegex(ValueError, "time in HH:MM format is required"):
            self.client.find_spx_credit_spread(
                "CALL", date=date(2026, 10, 16)
            )

        self.client._client.option_chains.assert_not_called()

    def test_future_date_requests_matching_option_chain(self):
        market_date = date(2026, 10, 20)
        expiration_code = market_date.strftime("%y%m%d")
        chain_response = Mock(
            status_code=200,
            json=Mock(
                return_value={
                    "putExpDateMap": {
                        "2026-10-20:3": {
                            "4990.0": [
                                {
                                    "symbol": f"SPXW  {expiration_code}P04990000",
                                    "delta": -0.19,
                                    "bid": 2.50,
                                    "ask": 2.70,
                                }
                            ],
                            "4980.0": [
                                {
                                    "symbol": f"SPXW  {expiration_code}P04980000",
                                    "delta": -0.10,
                                    "bid": 1.00,
                                    "ask": 1.20,
                                }
                            ],
                        }
                    }
                }
            ),
        )
        self.client._client.option_chains.return_value = chain_response

        result = self.client.find_spx_credit_spread("PUT", date=market_date)

        chain_kwargs = self.client._client.option_chains.call_args.kwargs
        self.assertEqual(chain_kwargs["fromDate"], "2026-10-20")
        self.assertEqual(chain_kwargs["toDate"], "2026-10-20")
        self.assertNotIn("daysToExpiration", chain_kwargs)
        self.assertEqual(result["sell_strike"], 4990)

    def test_loads_the_exact_past_quote_snapshot(self):
        market_date = date(2026, 10, 16)
        with tempfile.TemporaryDirectory() as temp_dir:
            quote_file = Path(temp_dir) / "spx_quote_20261016.csv"
            quote_file.write_text(
                "2026-10-16 09:30;5000;5010;SPXW  261016C05000000;2.5;2.7;delta=0.19\n"
                "2026-10-16 09:30;5010;5010;SPXW  261016C05010000;1.0;1.2;delta=0.10\n"
                "2026-10-16 09:31;5000;5011;SPXW  261016C05000000;3.0;3.2;delta=0.20\n",
                encoding="utf-8",
            )

            chain = SchwabClient._load_spx_quote_snapshot(
                quote_file, market_date, datetime.strptime("09:30", "%H:%M").time(), "CALL"
            )

        self.assertEqual(chain["5000.0"][0]["bid"], 2.5)
        self.assertEqual(chain["5000.0"][0]["delta"], 0.19)
        self.assertEqual(len(chain), 2)


if __name__ == "__main__":
    unittest.main()