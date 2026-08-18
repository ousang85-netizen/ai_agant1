"""Simple data retrieval utilities using yfinance."""

import pandas as pd
import yfinance as yf


def get_data(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Download historical data for a given symbol.

    Args:
        symbol: Ticker symbol such as 'AAPL'.
        period: Data period (e.g. '1y', '6mo').
        interval: Data interval ('1d', '1wk', etc.).

    Returns:
        DataFrame with Yahoo Finance OHLCV data indexed by Date.
    """
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    return df
