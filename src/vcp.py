"""Simple VCP (Volatility Contraction Pattern) checker."""

from typing import Tuple

import pandas as pd
import yfinance as yf


def get_daily_data(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        raise ValueError(f"No data for symbol {symbol}")
    return df


def vcp_contraction_score(df: pd.DataFrame, window: int = 21) -> float:
    """Compute a simple volatility contraction score over windows.

    Lower scores indicate stronger contraction.
    """
    if len(df) < (window * 4) - 1:
        return float("nan")

    highs = df["High"].rolling(window).max()
    lows = df["Low"].rolling(window).min()
    ranges = highs - lows
    avg = ranges[-window:] .mean()
    prev = ranges[-window * 2:-window].mean()
    prior = ranges[-window * 3:-window * 2].mean()
    if any(pd.isna(x) for x in [avg, prev, prior]) or prev <= 0 or prior <= 0:
        return float("nan")    

    return avg / max(prev, prior)


def is_vcp_pattern(df: pd.DataFrame, contraction_threshold: float = 0.8, lookback_days: int = 251) -> Tuple[bool, float]:
    """Return whether the given price series matches a simple VCP-like contraction pattern.

    The check uses decreasing volatility over successive windows and flattening range.
    """
    if len(df) < lookback_days:
        raise ValueError(f"Need at least {lookback_days} days for VCP check")

    recent = df.tail(lookback_days)
    score = vcp_contraction_score(recent)
    if pd.isna(score):
        return False, float("nan")
    return score < contraction_threshold, float(score)


def check_ticker_vcp(symbol: str, period: str = "1y", interval: str = "1d") -> Tuple[bool, float]:
    df = get_daily_data(symbol, period=period, interval=interval)
    if isinstance(df.columns, pd.MultiIndex):
        if symbol is None:
            raise ValueError("DataFrame has MultiIndex columns. Please provide a ticker name.")
        df_single = pd.DataFrame({
            "High": df["High"][symbol],
            "Low": df["Low"][symbol]
        })
    else:
        df_single = df
        
    return is_vcp_pattern(df_single)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Check if ticker matches a simple VCP pattern.")
    parser.add_argument("symbol", help="Ticker symbol to analyze")
    parser.add_argument("--period", default="1y", help="Data period for yfinance")
    parser.add_argument("--interval", default="1d", help="Data interval for yfinance")
    args = parser.parse_args()

    match, score = check_ticker_vcp(args.symbol, period=args.period, interval=args.interval)
    print(f"Ticker: {args.symbol}")
    print(f"VCP match: {match}")
    print(f"Volatility contraction score: {score:.4f}")


if __name__ == "__main__":
    main()
