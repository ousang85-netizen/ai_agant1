"""Replay an option order against saved intraday quote snapshots."""

from pathlib import Path
import math
import re
import time
from typing import Any, Dict, Optional, Sequence, Union

import pandas as pd
from datetime import date, datetime, time as datetime_time, timedelta

try:
    from .constants import (
        DEFAULT_BUTTERFLY_LEG_INTERVAL,
        DEFAULT_SPREAD_LEG_INTERVAL,
        OPTION_PRICE_SCALE,
        OPTION_PRICE_INCREMENT,
        SPXW_OPTION_PREFIX,
    )
except ImportError:
    from constants import (
        DEFAULT_BUTTERFLY_LEG_INTERVAL,
        DEFAULT_SPREAD_LEG_INTERVAL,
        OPTION_PRICE_SCALE,
        OPTION_PRICE_INCREMENT,
        SPXW_OPTION_PREFIX,
    )

class OptionTradeChart:
    """Calculate and plot estimated P/L from a semicolon-delimited quote file."""

    COLUMNS = ["timestamp", "strike", "underlying_price", "symbol", "bid", "ask", "delta"]

    def __init__(self, quote_file: Union[str, Path]):
        self.quote_file = Path(quote_file)
        try:
            quotes = pd.read_csv(
                self.quote_file,
                sep=";",
                header=None,
                names=self.COLUMNS,
                dtype={"symbol": str},
            )
        except (OSError, pd.errors.ParserError) as error:
            raise ValueError(f"Could not read option quotes from {self.quote_file}") from error

        if quotes.empty:
            raise ValueError(f"No option quotes found in {self.quote_file}")

        quotes["timestamp"] = pd.to_datetime(quotes["timestamp"], errors="coerce")
        for column in ("strike", "underlying_price", "bid", "ask"):
            quotes[column] = pd.to_numeric(quotes[column], errors="coerce")
        quotes["delta"] = pd.to_numeric(
            quotes["delta"].astype(str).str.removeprefix("delta="), errors="coerce"
        )
        if quotes[["timestamp", "symbol", "bid", "ask"]].isna().any().any():
            raise ValueError(f"Quote file contains invalid rows: {self.quote_file}")
        self.quotes = quotes.sort_values("timestamp").reset_index(drop=True)

    def add_one_minute(self, timestamp: Union[str, pd.Timestamp]) -> pd.Timestamp:
        """Return a timestamp one minute later than the input."""
        ts = pd.Timestamp(timestamp)
        if ts.second != 0 or ts.microsecond != 0:
            raise ValueError("timestamp must be at the start of a minute")
        return ts + timedelta(minutes=1)

    @classmethod
    def plot_command(
        cls,
        command: str,
        entry_date: Union[str, date],
        entry_time: Union[str, datetime_time, datetime, pd.Timestamp],
        data_dir: Union[str, Path] = "data",
    ):
        """Build and plot a supported ``buy spread/fly at <strike>`` command."""
        match = re.fullmatch(
            r"buy\s+(?P<strategy>spread|fly)\s+at\s+(?P<strike>\d+(?:\.\d+)?)",
            command.strip(),
            flags=re.IGNORECASE,
        )
        if not match:
            raise ValueError(
                "command must be 'buy spread at <strike>' or 'buy fly at <strike>'"
            )

        if isinstance(entry_date, datetime):
            trade_date = entry_date.date()
        elif isinstance(entry_date, date):
            trade_date = entry_date
        else:
            try:
                trade_date = date.fromisoformat(entry_date)
            except (TypeError, ValueError) as error:
                raise ValueError("entry_date must be a date in YYYY-MM-DD format") from error

        if isinstance(entry_time, datetime):
            trade_time = entry_time.time()
        elif isinstance(entry_time, pd.Timestamp):
            trade_time = entry_time.time()
        elif isinstance(entry_time, datetime_time):
            trade_time = entry_time
        else:
            try:
                trade_time = datetime_time.fromisoformat(entry_time)
            except (TypeError, ValueError) as error:
                raise ValueError("entry_time must be a time in HH:MM[:SS] format") from error

        entry_timestamp = datetime.combine(trade_date, trade_time)
        quote_file = Path(data_dir) / f"spx_quote_{trade_date:%Y%m%d}.csv"
        chart = cls(quote_file)
        earlier_quotes = chart.quotes[
            chart.quotes["timestamp"] <= pd.Timestamp(entry_timestamp)
        ]
        if earlier_quotes.empty:
            raise ValueError(f"No underlying quote at or before {entry_timestamp}")
        try:
            underlying_price = float(earlier_quotes.iloc[-1]["underlying_price"])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"No valid underlying price at or before {entry_timestamp}"
            ) from error
        if not math.isfinite(underlying_price) or underlying_price <= 0:
            raise ValueError(
                f"No valid underlying price at or before {entry_timestamp}"
            )

        strategy = match.group("strategy").lower()
        center_strike = float(match.group("strike"))

        def option_symbol(strike: float, option_type: str) -> str:
            strike_code = f"{int(round(strike * 1000)):08d}"
            return f"{SPXW_OPTION_PREFIX}  {trade_date:%y%m%d}{option_type}{strike_code}"

        def make_leg(instruction: str, quantity: int, symbol: str) -> Dict[str, Any]:
            return {
                "instruction": instruction,
                "quantity": str(quantity),
                "instrument": {"symbol": symbol, "assetType": "OPTION"},
            }

        legs: list[Dict[str, Any]]
        if strategy == "spread":
            option_type = "P" if underlying_price > center_strike else "C"
            buy_strike = (
                center_strike - DEFAULT_SPREAD_LEG_INTERVAL
                if option_type == "P"
                else center_strike + DEFAULT_SPREAD_LEG_INTERVAL
            )
            legs = [
                make_leg(
                    "SELL_TO_OPEN",
                    1,
                    option_symbol(center_strike, option_type),
                ),
                make_leg(
                    "BUY_TO_OPEN",
                    1,
                    option_symbol(buy_strike, option_type),
                ),
            ]
        else:
            option_type = "P" if underlying_price >= center_strike else "C"
            interval = DEFAULT_BUTTERFLY_LEG_INTERVAL
            legs = [
                make_leg("BUY_TO_OPEN", 1, option_symbol(center_strike - interval, option_type)),
                make_leg("SELL_TO_OPEN", 2, option_symbol(center_strike, option_type)),
                make_leg("BUY_TO_OPEN", 1, option_symbol(center_strike + interval, option_type)),
            ]

        order = {"orderLegCollection": legs}
        return chart.plot_trade(order, entry_timestamp)
    
    def calculate_profit_loss(
        self,
        order: Dict[str, Any],
        entry_time: Union[str, pd.Timestamp],
        multiplier: int = 100,
    ) -> pd.DataFrame:
        """Return estimated position P/L at each saved quote time from entry onward.

        ``order`` uses Schwab's ``orderLegCollection`` shape. Entry and mark prices
        use the rounded bid/ask midpoint. Fees and slippage are not included.
        """
        def calc_price(quote):
            price = (quote["bid"] + quote["ask"]) / 2
            price = round(price * OPTION_PRICE_SCALE) / OPTION_PRICE_SCALE
            return price * multiplier
        
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        legs = order.get("orderLegCollection", [])
        if not legs:
            raise ValueError("order must contain at least one option leg")

        entry_timestamp = pd.Timestamp(entry_time)
        parsed_legs = []
        cost = 0.0
        for leg in legs:
            instruction = str(leg.get("instruction", "")).upper()
            # this is used at opposite side when close the position
            if instruction.startswith("BUY"):
                direction = 1
            elif instruction.startswith("SELL"):
                direction = -1
                fill_side = "ask"
                mark_side = "bid"
            else:
                raise ValueError(f"Unsupported option instruction: {instruction}")

            symbol = leg.get("instrument", {}).get("symbol")
            try:
                quantity = float(leg["quantity"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("each option leg must have a numeric quantity") from error
            if not symbol or quantity <= 0:
                raise ValueError("each option leg must have a symbol and positive quantity")

            contract_quotes = self.quotes[self.quotes["symbol"] == symbol]
            for try_5_times in range(5):
                entry_quotes = contract_quotes[contract_quotes["timestamp"] <= entry_timestamp]
                if not entry_quotes.empty:
                    break
                entry_timestamp = self.add_one_minute(entry_timestamp)
            #entry_quotes = contract_quotes[contract_quotes["timestamp"] <= entry_timestamp]

            if entry_quotes.empty:
                raise ValueError(f"No quote for {symbol} at or before {entry_timestamp}")
            entry_quote = entry_quotes.iloc[-1]
            cost += direction * quantity * calc_price(entry_quote) 
            parsed_legs.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "direction": direction,
                    "fill_price": calc_price(entry_quote),
                    "quotes": contract_quotes.set_index("timestamp").apply(
                        calc_price, axis=1
                    ).sort_index(),
                }
            )

        quote_times = self.quotes.loc[
            self.quotes["timestamp"] >= entry_timestamp, "timestamp"
        ].drop_duplicates()
        timestamps = pd.DatetimeIndex([entry_timestamp]).union(pd.DatetimeIndex(quote_times)).sort_values()
        profit_loss = pd.Series(-cost, index=timestamps)
        for leg in parsed_legs:
            fills = leg["quotes"].groupby(level=0).last().reindex(timestamps).ffill()
            fills.loc[entry_timestamp] = leg["fill_price"]
            fills = fills.sort_index().ffill()
            profit_loss += (
                leg["direction"]
                * leg["quantity"]
                * fills
            )

        history = pd.DataFrame(
            {"profit_loss": profit_loss}, index=timestamps
        ).rename_axis("timestamp")
        history.attrs["net_entry_cost"] = cost
        return history

    def plot_trade(
        self,
        order: Union[Dict[str, Any], Sequence[Dict[str, Any]]],
        entry_time: Union[
            str,
            datetime,
            pd.Timestamp,
            Sequence[Union[str, datetime, pd.Timestamp]],
        ],
        output_file: Optional[Union[str, Path]] = None,
        multiplier: int = 100,
    ):
        """Plot one trade or the combined P/L of several trades.

        When ``order`` is a sequence, ``entry_time`` can be one timestamp shared
        by all orders or a matching sequence of timestamps.
        """
        import matplotlib.pyplot as plt

        orders = [order] if isinstance(order, dict) else list(order)
        if not orders or any(not isinstance(trade_order, dict) for trade_order in orders):
            raise ValueError("order must be an order dictionary or a non-empty sequence of orders")

        if isinstance(entry_time, (str, datetime, pd.Timestamp)):
            entry_times = [entry_time] * len(orders)
        else:
            entry_times = list(entry_time)
            if len(entry_times) != len(orders):
                raise ValueError("entry_time sequence must contain one timestamp per order")

        trade_histories = [
            self.calculate_profit_loss(
                trade_order, trade_entry_time, multiplier=multiplier
            )
            for trade_order, trade_entry_time in zip(orders, entry_times)
        ]
        histories = [trade_history["profit_loss"] for trade_history in trade_histories]
        net_entry_cost = sum(
            trade_history.attrs["net_entry_cost"] for trade_history in trade_histories
        )
        combined_pnl = pd.concat(histories, axis=1).sort_index().ffill().fillna(0).sum(axis=1)
        history = combined_pnl.to_frame(name="profit_loss")
        figure, axis = plt.subplots(figsize=(12, 6))
        axis.plot(history.index, history["profit_loss"], color="#176b5b", linewidth=2)
        axis.axhline(0, color="#555555", linewidth=1, linestyle="--")
        axis.fill_between(
            history.index,
            history["profit_loss"],
            0,
            where=history["profit_loss"] >= 0,
            color="#55a88c",
            alpha=0.2,
        )
        axis.fill_between(
            history.index,
            history["profit_loss"],
            0,
            where=history["profit_loss"] < 0,
            color="#d45b55",
            alpha=0.2,
        )
        axis.set_title("Estimated Option Trade P/L")
        if net_entry_cost >= 0:
            cost_label = f"Net entry debit: ${net_entry_cost:,.2f}"
        else:
            cost_label = f"Net entry credit: ${-net_entry_cost:,.2f}"
        axis.text(
            0.02,
            0.98,
            cost_label,
            transform=axis.transAxes,
            verticalalignment="top",
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "#cccccc"},
        )
        axis.set_xlabel("Time")
        axis.set_ylabel("Profit / Loss ($)")
        axis.grid(True, alpha=0.25)
        figure.autofmt_xdate()
        figure.tight_layout()
        if output_file is not None:
            figure.savefig(output_file)
        plt.show()
        return figure, axis


def main() -> None:
    """Interactively replay spread and butterfly trades from saved quotes."""
    current_date = date.today()
    while True:
        try:
            command = input(
                "Command ('buy spread at <strike>', 'buy fly at <strike>', "
                "'date [YYYY-MM-DD]', or 'quit'): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        normalized_command = command.lower()
        if normalized_command in {"quit", "exit", "q"}:
            break
        if normalized_command == "date" or normalized_command.startswith("date "):
            date_value = command[4:].strip()
            if not date_value:
                try:
                    date_value = input("Current date (YYYY-MM-DD): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
            try:
                current_date = date.fromisoformat(date_value)
            except ValueError:
                print("Date must be in YYYY-MM-DD format.")
                continue
            print(f"Using date {current_date.isoformat()}.")
            continue

        if not re.match(r"buy\s+(?:spread|fly)\b", command, flags=re.IGNORECASE):
            print(
                "Enter 'buy spread at <strike>', 'buy fly at <strike>', "
                "'date [YYYY-MM-DD]', or 'quit'."
            )
            continue

        try:
            entry_time = input("Entry time (HH:MM): ").strip()
            OptionTradeChart.plot_command(
                command, current_date.isoformat(), entry_time
            )
        except (EOFError, KeyboardInterrupt):
            print()
            break
        except ValueError as error:
            print(f"Could not plot trade: {error}")


if __name__ == "__main__":
    main()