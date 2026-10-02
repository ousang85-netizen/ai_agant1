import csv
import os
import tempfile
import threading
import unittest
from datetime import datetime
from unittest.mock import Mock

from src.order_manager import OrderManager


class TestOrderManager(unittest.TestCase):
    def test_init_restores_unique_active_orders_from_daily_file(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(
                directory, f"orders_{datetime.now().strftime('%Y%m%d')}.csv"
            )
            with open(filename, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(OrderManager._fields)
                writer.writerow(
                    ["123", "submitted", "updated-1", "ABC", "BUY", 5, 10,
                     "SUBMITTED", "", "", "", "", ""]
                )
                writer.writerow(
                    ["123", "submitted", "updated-2", "ABC", "BUY", 5, 10,
                     "PENDING_ACTIVATION", 0, "", "", "", ""]
                )
                writer.writerow(
                    ["456", "submitted", "updated", "XYZ", "SELL", 2, 20,
                     "CANCELED", "", "", "", "", ""]
                )

            manager = OrderManager(Mock(), poll_interval=60, data_directory=directory)
            try:
                self.assertEqual(list(manager._orders), ["123"])
                self.assertEqual(manager._orders["123"]["symbol"], "ABC")
                self.assertEqual(manager._orders["123"]["quantity"], 5)
                self.assertEqual(manager._orders["123"]["limit_price"], 10.0)
            finally:
                manager.stop(timeout=1.0)

    def test_filled_order_is_logged_with_current_profit_loss(self):
        details_read = threading.Event()
        broker = Mock()
        broker.get_client.return_value.order_details.return_value.json.return_value = {
            "status": "FILLED",
            "orderLegCollection": [
                {
                    "legId": 1,
                    "instruction": "BUY",
                    "instrument": {"symbol": "ABC", "assetType": "EQUITY"},
                }
            ],
            "orderActivityCollection": [
                {
                    "executionLegs": [
                        {"legId": 1, "quantity": 5, "price": 10.0}
                    ]
                }
            ],
        }

        def read_order_details(*args):
            details_read.set()
            return broker.get_client.return_value.order_details.return_value

        broker.get_client.return_value.order_details.side_effect = read_order_details
        broker.get_quote.return_value = {"ABC": {"quote": {"lastPrice": 12.0}}}

        with tempfile.TemporaryDirectory() as directory:
            manager = OrderManager(broker, poll_interval=0.01, data_directory=directory)
            try:
                manager.record_order(
                    "123",
                    "ABC",
                    5,
                    "BUY",
                    10.0,
                    {
                        "orderLegCollection": [
                            {
                                "legId": 1,
                                "instruction": "BUY",
                                "instrument": {
                                    "symbol": "ABC",
                                    "assetType": "EQUITY",
                                },
                            }
                        ]
                    },
                )
                self.assertTrue(details_read.wait(timeout=1.0))
            finally:
                manager.stop(timeout=1.0)

            filename = os.path.join(
                directory,
                f"status_check_{datetime.now().strftime('%Y%m%d')}.csv",
            )
            with open(filename, newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

        fill_row = next(row for row in rows if row["status"] == "FILLED")
        self.assertEqual(float(fill_row["filled_quantity"]), 5.0)
        self.assertEqual(float(fill_row["current_price"]), 12.0)
        self.assertEqual(float(fill_row["profit_loss"]), 10.0)


if __name__ == "__main__":
    unittest.main()