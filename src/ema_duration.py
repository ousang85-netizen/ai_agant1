"""Measure how many consecutive bars a stock has closed above its EMA."""

import argparse

import pandas as pd

from .data import get_data


class EmaDuration:
    """Calculate how long a stock has stayed above its exponential average."""

    def __init__(
        self, period: int = 10, data_period: str = "1y", interval: str = "1d"
    ):
        if period < 1:
            raise ValueError("period must be at least 1")
        self.period = period
        self.data_period = data_period
        self.interval = interval

    def count_above(self, close_prices: pd.Series | list[float]) -> int:
        """Return consecutive recent bars whose close is strictly above EMA."""
        closes = pd.Series(close_prices, dtype="float64").dropna()
        if closes.empty:
            return 0

        ema = closes.ewm(span=self.period, adjust=False).mean()
        count = 0
        for is_above in reversed((closes > ema).tolist()):
            if not is_above:
                break
            count += 1
        return count

    def for_stock(self, symbol: str) -> int:
        """Download stock history and return its current EMA duration."""
        data = get_data(
            symbol, period=self.data_period, interval=self.interval
        )
        if data.empty or "Close" not in data.columns:
            raise ValueError(f"No usable Close data returned for {symbol}")

        close = data["Close"] 
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return self.count_above(close)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count consecutive recent bars with a close above a stock's EMA."
    )
    parser.add_argument("symbol", help="Ticker symbol, for example AAPL")
    parser.add_argument("--period", type=int, default=10, help="EMA span (default: 10)")
    parser.add_argument("--history", default="1y", help="Yahoo Finance history period")
    parser.add_argument("--interval", default="1d", help="Yahoo Finance bar interval")
    args = parser.parse_args()

    calculator = EmaDuration(args.period, args.history, args.interval)
    count = calculator.for_stock(args.symbol.upper())
    unit = "bar" if count == 1 else "bars"
    print(f"{args.symbol.upper()} has stayed above its {args.period} EMA for {count} {unit}.")


if __name__ == "__main__":
    main()