"""Replay an option order against saved intraday quote snapshots."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd


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

    def calculate_profit_loss(
        self,
        order: Dict[str, Any],
        entry_time: Union[str, pd.Timestamp],
        multiplier: int = 100,
    ) -> pd.DataFrame:
        """Return estimated position P/L at each saved quote time from entry onward.

        ``order`` uses Schwab's ``orderLegCollection`` shape. Opening buys are
        assumed filled at ask and opening sells at bid; open positions are marked
        at bid when long and ask when short. Fees and slippage are not included.
        """
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        legs = order.get("orderLegCollection", [])
        if not legs:
            raise ValueError("order must contain at least one option leg")

        entry_timestamp = pd.Timestamp(entry_time)
        parsed_legs = []
        for leg in legs:
            instruction = str(leg.get("instruction", "")).upper()
            if instruction.startswith("BUY"):
                direction = 1
                fill_side = "ask"
                mark_side = "bid"
            elif instruction.startswith("SELL"):
                direction = -1
                fill_side = "bid"
                mark_side = "ask"
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
            entry_quotes = contract_quotes[contract_quotes["timestamp"] <= entry_timestamp]
            if entry_quotes.empty:
                raise ValueError(f"No quote for {symbol} at or before {entry_timestamp}")
            entry_quote = entry_quotes.iloc[-1]
            parsed_legs.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "direction": direction,
                    "fill_price": float(entry_quote[fill_side]),
                    "mark_side": mark_side,
                    "entry_mark": float(entry_quote[mark_side]),
                    "quotes": contract_quotes.set_index("timestamp")[mark_side],
                }
            )

        quote_times = self.quotes.loc[
            self.quotes["timestamp"] >= entry_timestamp, "timestamp"
        ].drop_duplicates()
        timestamps = pd.DatetimeIndex([entry_timestamp]).union(pd.DatetimeIndex(quote_times)).sort_values()
        profit_loss = pd.Series(0.0, index=timestamps)
        for leg in parsed_legs:
            marks = leg["quotes"].groupby(level=0).last().reindex(timestamps).ffill()
            marks.loc[entry_timestamp] = leg["entry_mark"]
            marks = marks.sort_index().ffill()
            profit_loss += (
                leg["direction"]
                * leg["quantity"]
                * (marks - leg["fill_price"])
                * multiplier
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
        return figure, axis