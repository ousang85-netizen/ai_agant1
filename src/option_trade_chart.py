"""Replay an option order against saved intraday quote snapshots."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd
from datetime import date, datetime, timedelta

from constants import OPTION_PRICE_SCALE, OPTION_PRICE_INCREMENT

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

        return pd.DataFrame({"profit_loss": profit_loss}, index=timestamps).rename_axis("timestamp")

    def plot_trade(
        self,
        order: Dict[str, Any],
        entry_time: Union[str, pd.Timestamp],
        output_file: Optional[Union[str, Path]] = None,
        multiplier: int = 100,
    ):
        """Plot estimated intraday P/L and optionally save the figure."""
        import matplotlib.pyplot as plt

        history = self.calculate_profit_loss(order, entry_time, multiplier=multiplier)
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
        axis.set_xlabel("Time")
        axis.set_ylabel("Profit / Loss ($)")
        axis.grid(True, alpha=0.25)
        figure.autofmt_xdate()
        figure.tight_layout()
        if output_file is not None:
            figure.savefig(output_file)
        plt.show()
        return figure, axis


if __name__ == "__main__":
    cur = datetime.now()
    #also defined in agent.py, but this is for testing the OptionTradeChart class independently
    #spx_quote_filename = f"data/spx_quote_{cur.strftime('%Y%m%d')}.csv"
    spx_quote_filename = "data/spx_quote_20261009.csv"
    chart = OptionTradeChart(spx_quote_filename)

    legs = [
        {
            "instruction": instruction,
            "quantity": quantity,
            "instrument": {
                "symbol": option_symbol,
                "assetType": "OPTION",
            },
        }
        for instruction, quantity, option_symbol in (
            ("BUY_TO_OPEN", "1",  "SPXW  261009C07840000"),
            ("SELL_TO_OPEN", "1", "SPXW  261009C07830000"),
        )
    ]
    order = {
        "orderLegCollection": legs
    }

    
    chart.plot_trade(
        order=order,
        entry_time="2026-10-09 06:35:27",
    )