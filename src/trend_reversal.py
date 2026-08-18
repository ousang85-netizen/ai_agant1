"""Simple trend reversal detector using moving average crossover."""

from typing import Tuple

import pandas as pd
import yfinance as yf


def get_daily_data(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        raise ValueError(f"No data for symbol {symbol}")
    return df

def ibd_powertrend(df: pd.DataFrame, short_window: int = 50, long_window: int = 200) -> Tuple[str, pd.Timestamp]:
    """  this is criteria for IBD PowerTrend detection
    1. day's low is above 21 EMA
    2. 21 ema is above 50 ma for at least 5 days
    3. 50 day line is in an upward trend for at least 1 days
    4. market close up for the day

    How the trend ends:
    1. 21 day crossover below 50 day
    2. or circuit break 
    3. or a follow-through day failure
    """


def detect_trend_reversal(df: pd.DataFrame, short_window: int = 50, long_window: int = 200) -> Tuple[str, pd.Timestamp]:
    """Detect trend reversal using moving average crossover.

    Returns the type of reversal ('bullish', 'bearish', or 'none') and the date of the crossover.
    Bullish reversal: short MA crosses above long MA.
    Bearish reversal: short MA crosses below long MA.
    """
    if len(df) < long_window:
        raise ValueError(f"Need at least {long_window} days for trend reversal check")

    # Calculate moving averages
    df = df.copy()
    df['Short_MA'] = df['Close'].rolling(window=short_window).mean()
    df['Long_MA'] = df['Close'].rolling(window=long_window).mean()

    # Find crossovers
    df['Signal'] = (df['Short_MA'] > df['Long_MA']).astype(int)
    df['Crossover'] = df['Signal'].diff()

    # Find the most recent crossover
    crossovers = df[df['Crossover'] != 0]
    if crossovers.empty:
        return 'none', pd.NaT

    last_crossover = crossovers.iloc[-1]
    if last_crossover['Crossover'].item() > 0:
        return 'bullish', last_crossover.name
    else:
        return 'bearish', last_crossover.name


def check_ticker_trend_reversal(symbol: str, period: str = "2y", interval: str = "1d", short_window: int = 50, long_window: int = 200) -> Tuple[str, pd.Timestamp]:
    df = get_daily_data(symbol, period=period, interval=interval)
    return detect_trend_reversal(df, short_window=short_window, long_window=long_window)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Detect trend reversal for a ticker using MA crossover.")
    parser.add_argument("symbol", help="Ticker symbol to analyze")
    parser.add_argument("--period", default="2y", help="Data period for yfinance")
    parser.add_argument("--interval", default="1d", help="Data interval for yfinance")
    parser.add_argument("--short-window", type=int, default=50, help="Short moving average window")
    parser.add_argument("--long-window", type=int, default=200, help="Long moving average window")
    args = parser.parse_args()

    reversal, date = check_ticker_trend_reversal(args.symbol, period=args.period, interval=args.interval,
                                                 short_window=args.short_window, long_window=args.long_window)
    print(f"Ticker: {args.symbol}")
    print(f"Trend reversal: {reversal}")
    if reversal != 'none':
        print(f"Crossover date: {date.date()}")


if __name__ == "__main__":
    main()