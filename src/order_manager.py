"""Persist submitted orders and monitor their status and mark-to-market P&L."""

import csv
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional
import re

class OrderManager:
    """Track Schwab orders in daily CSV files using a background polling thread."""

    _fields = (
        "order_id",
        "submitted_at",
        "updated_at",
        "symbol",
        "action",
        "quantity",
        "limit_price",
        "status",
        "filled_quantity",
        "average_fill_price",
        "current_price",
        "profit_loss",
        "error",
    )
    _filled_statuses = {"FILLED", "PARTIALLY_FILLED"}
    _terminal_statuses = {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED", "REPLACED"}

    def __init__(
        self,
        broker: Any,
        poll_interval: float = 20.0,
        data_directory: str = "data",
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self._broker = broker
        self._poll_interval = poll_interval
        self._data_directory = data_directory
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        os.makedirs(self._data_directory, exist_ok=True)
        self.order_file_name = os.path.join(
                self._data_directory,
                f"orders_{datetime.now().strftime('%Y%m%d')}.csv",)
        
        self.status_check_file_name = os.path.join(
                self._data_directory,
                f"status_check_{datetime.now().strftime('%Y%m%d')}.csv",
            )

        self._load_order_book()

        '''
        if self._orders:
            self._thread = threading.Thread(
                target=self._monitor_orders,
                name="order-monitor",
                daemon=True,
            )
            self._thread.start()
        '''
    @staticmethod
    def convert_option_ticker(ticker: str) -> str:
        """
        Converts an option ticker string format to a shorter code format.
        Example: ":SPXW 260929C07685000" -> "7685C"
        """
        # Regex splits into option type (C/P) and strike price padding
        match = re.search(r'([CP])0*(\d+)\d{3}$', ticker)
        if not match:
            return ticker
            
        option_type, strike = match.groups()
        return f"{strike}{option_type}"

    def simple_order_str(self, order_detail):


        # Use .get() with a default value to prevent KeyErrors
        strategy = order_detail.get('complexOrderStrategyType', 'NONE')
        legs = order_detail.get('orderLegCollection', [])
        
        # Format the strategy prefix (handles BUTTERFLY, VERTICAL, etc. dynamically)
        desc_parts = []
        if strategy and strategy != 'NONE':
            # Capitalizes 'BUTTERFLY' to 'Butterfly'
            desc_parts.append(f"{strategy.title()}; ")
        
        # Build leg descriptions cleanly without trailing colons
        leg_strings = []
        for leg in legs:
            instruction = leg.get('instruction', '')
            symbol =  OrderManager.convert_option_ticker(leg.get('instrument',None).get('symbol', ''))
            leg_strings.append(f"{instruction}:{symbol}")
        
        # Join legs with a delimiter, then combine with the strategy prefix
        desc_parts.append(":".join(leg_strings))
        
        return "".join(desc_parts)

    def _load_order_book(self) -> None:
        """Restore the latest record for each nonterminal order in today's file."""
        if not os.path.isfile(self.order_file_name):
            return

        with open(self.order_file_name, newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                order_id = (row.get("order_id") or "").strip()
                if not order_id:
                    continue

                try:
                    quantity = int(row.get("quantity") or 0)
                    price = float(row["limit_price"]) if row.get("limit_price") else None
                except (KeyError, TypeError, ValueError):
                    continue

                action = (row.get("action") or "").upper()
                symbol = (row.get("symbol") or "").strip()
                if not symbol or quantity <= 0:
                    continue
                status = (row.get("status") or "").upper()
                if status in self._terminal_statuses:
                    self._orders.pop(order_id, None)
                    continue

                self._orders[order_id] = {
                    "order_id": order_id,
                    "submitted_at": row.get("submitted_at") or "",
                    "symbol": symbol,
                    "action": action,
                    "quantity": quantity,
                    "limit_price": price,
                    "order": {
                        "orderLegCollection": [
                            {
                                "instruction": action,
                                "quantity": str(quantity),
                                "instrument": {
                                    "symbol": symbol,
                                    "assetType": "EQUITY",
                                },
                            }
                        ]
                    },
                }

    def record_order(
        self,
        order_id: str,
        symbol: str,
        quantity: int,
        action: str,
        price: Optional[float],
        order: Dict[str, Any],
    ) -> None:
        """Record an accepted order and start monitoring it if needed."""
        if not order_id:
            return
        submitted_at = datetime.now().astimezone().isoformat(timespec="seconds")
        record = {
            "order_id": str(order_id),
            "submitted_at": submitted_at,
            "symbol": symbol,
            "action": action.upper(),
            "quantity": quantity,
            "limit_price": price,
            "order": order,
        }
        with self._lock:
            self._orders[str(order_id)] = record
            self._append_snapshot(record, status="SUBMITTED", to_order_book = True)
            '''
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._monitor_orders,
                    name="order-monitor",
                    daemon=True,
                )
                self._thread.start()
            '''

    def start_monitor_thread(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._monitor_orders,
                    name="order-monitor",
                    daemon=True,
                )
                self._thread.start()

    def stop(self, timeout: Optional[float] = None) -> None:
        """Stop the monitor thread cleanly."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def _monitor_orders(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                orders = list(self._orders.values())
            if orders:
                filename = self.status_check_file_name
                with open(filename, "a", newline="", encoding="utf-8") as file:
                    file.write(f"{datetime.now()}\n")                 
                for record in orders:
                    if self._stop_event.is_set():
                        break
                    self._check_order(record)
           
                with open(filename, "a", newline="", encoding="utf-8") as file:
                    file.write("-" * 30 + "\n")
            self._stop_event.wait(self._poll_interval)

    def _check_order(self, record: Dict[str, Any]) -> None:
        try:
            response = self._broker.get_client().order_details(
                self._broker.get_hash_value(), record["order_id"]
            )
            details = response.json() if hasattr(response, "json") else response
            if not isinstance(details, dict):
                raise ValueError("order details response was not an object")

            status = str(details.get("status", "UNKNOWN")).upper()
            pnl = None
            filled_quantity = 0
            average_fill_price = None
            current_price = None
            if status in self._filled_statuses:
                pnl, filled_quantity, average_fill_price, current_price = (
                    self._calculate_profit_loss(record, details)
                )
            if status not in self._terminal_statuses:
                desc=self.simple_order_str(details)
                #if desc == None or pnl == 0.:
                #    print("break here")
                self._append_snapshot(
                    record,
                    status=status,
                    filled_quantity=filled_quantity,
                    average_fill_price=average_fill_price,
                    current_price=current_price,
                    profit_loss=pnl,
                    error = "",
                    to_order_book = False,
                    simple_desc=desc,
                )

            if status in self._terminal_statuses:
                with self._lock:
                    self._orders.pop(record["order_id"], None)
        except Exception as error:
            self._append_snapshot(record, status="MONITOR_ERROR", error=str(error))

    def _calculate_profit_loss(self, record: Dict[str, Any], details: Dict[str, Any]):
        order_legs = details.get("orderLegCollection") or record["order"].get(
            "orderLegCollection", []
        )
        leg_by_id = {
            str(leg.get("legId", index + 1)): leg
            for index, leg in enumerate(order_legs)
        }
        executions = []
        for activity in details.get("orderActivityCollection", []):
            for execution in activity.get("executionLegs", []):
                leg = leg_by_id.get(str(execution.get("legId", 1)))
                if leg is None:
                    continue
                try:
                    executions.append(
                        {
                            "symbol": leg["instrument"]["symbol"],
                            "instruction": leg["instruction"].upper(),
                            "quantity": float(execution["quantity"]),
                            "price": float(execution["price"]),
                            "multiplier": 100.0
                            if leg.get("instrument", {}).get("assetType") == "OPTION"
                            else 1.0,
                        }
                    )
                except (KeyError, TypeError, ValueError):
                    continue

        if not executions:
            filled_quantity = float(
                details.get("filledQuantity", record["quantity"])
            )
            fill_price = details.get(
                "averagePrice", details.get("price", record["limit_price"])
            )
            if fill_price is None or filled_quantity <= 0:
                return None, 0, None, None
            leg = order_legs[0] if order_legs else {}
            instrument = leg.get("instrument", {})
            executions = [
                {
                    "symbol": instrument.get("symbol", record["symbol"]),
                    "instruction": leg.get("instruction", record["action"]).upper(),
                    "quantity": filled_quantity,
                    "price": float(fill_price),
                    "multiplier": 100.0
                    if instrument.get("assetType") == "OPTION"
                    else 1.0,
                }
            ]

        pnl = 0.0
        total_quantity = 0.0
        total_entry_value = 0.0
        total_current_value = 0.0
        for execution in executions:
            quote_data = self._broker.get_quote(execution["symbol"])
            quote = quote_data[execution["symbol"]]["quote"]
            mark = quote.get("lastPrice") or quote.get("mark")
            if mark is None and quote.get("bidPrice") and quote.get("askPrice"):
                mark = (float(quote["bidPrice"]) + float(quote["askPrice"])) / 2
            if mark is None:
                raise ValueError(f"no current quote for {execution['symbol']}")
            mark = float(mark)
            direction = -1.0 if execution["instruction"].startswith("SELL") else 1.0
            quantity = execution["quantity"]
            multiplier = execution["multiplier"]
            pnl += direction * (mark - execution["price"]) * quantity * multiplier
            total_quantity += quantity
            total_entry_value += execution["price"] * quantity
            total_current_value += mark * quantity

        average_fill_price = (
            total_entry_value / total_quantity if total_quantity else None
        )
        current_price = (
            total_current_value / total_quantity if total_quantity else None
        )
        return pnl, total_quantity, average_fill_price, current_price

    def _append_snapshot(
        self,
        record: Dict[str, Any],
        status: str,
        filled_quantity: Any = "",
        average_fill_price: Any = "",
        current_price: Any = "",
        profit_loss: float = 0.,
        error: str = "",
        to_order_book: bool = False,
        simple_desc: str = None
    ) -> None:
        row = {
            "order_id": record["order_id"],
            "submitted_at": record["submitted_at"],
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "symbol": record["symbol"],
            "action": record["action"],
            "quantity": record["quantity"],
            "limit_price": record["limit_price"],
            "status": status,
            "filled_quantity": filled_quantity,
            "average_fill_price": average_fill_price,
            "current_price": current_price,
            "profit_loss": profit_loss,
            "error": error,
        }

        if to_order_book:
            filename =  self.order_file_name
            with open(filename, "a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=self._fields)
                if file.tell() == 0:
                    writer.writeheader()
                writer.writerow(row)
        else:
            filename = self.status_check_file_name            
            with open(filename, "a", newline="", encoding="utf-8") as file:
                file.write(f"{simple_desc}; P/L: {profit_loss:.2f}\n")
                #writer = csv.DictWriter(file, fieldnames=self._fields)
                #if file.tell() == 0:
                #    writer.writeheader()
                #writer.writerow(row)