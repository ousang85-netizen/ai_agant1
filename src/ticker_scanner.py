"""Ticker scanning utilities for NYSE/NASDAQ with volume and close filters."""

from typing import Dict, List

import pandas as pd
from finvizfinance.screener.overview import Overview


def _normalize_price_filter(min_close: float) -> str:
    if min_close <= 1:
        return "Over $1"
    if min_close <= 2:
        return "Over $2"
    if min_close <= 3:
        return "Over $3"
    if min_close <= 4:
        return "Over $4"
    if min_close <= 5:
        return "Over $5"
    if min_close <= 7:
        return "Over $7"
    if min_close <= 10:
        return "Over $10"
    return "Over $20"


def _normalize_volume_filter(min_volume: int) -> str:
    if min_volume <= 500000:
        return "Over 500K"
    if min_volume <= 1000000:
        return "Over 1M"
    if min_volume <= 2000000:
        return "Over 2M"
    if min_volume <= 3000000:
        return "Over 3M"
    if min_volume <= 4000000:
        return "Over 4M"
    return "Over 5M"


def collect_high_volume_close_tickers(
    exchange: str,
    min_volume: int = 1500000,
    min_close: float = 5.0,
    limit: int = 5000,
 ) -> List[str]:
    """Collect high-volume and high-close tickers using Finviz screening."""
    exchange = exchange.upper().strip()
    if exchange not in {"NYSE", "NASDAQ"}:
        raise ValueError("exchange must be 'NYSE' or 'NASDAQ'")

    price_filter = _normalize_price_filter(min_close)
    volume_filter = _normalize_volume_filter(min_volume)

    ov = Overview()
    ov.set_filter(filters_dict={"Exchange": exchange, "Price": price_filter, "Average Volume": volume_filter})
    df = ov.screener_view(order="Ticker", limit=limit, verbose=0)
    if df is None or df.empty:
        return []

    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"].astype(str).str.replace(",", ""), errors="coerce")
    if "Price" in df.columns:
        df["Price"] = pd.to_numeric(df["Price"].astype(str).str.replace("$", "", regex=False), errors="coerce")

    if "Volume" in df.columns:
        df = df[df["Volume"] > min_volume]
    if "Price" in df.columns:
        df = df[df["Price"] > min_close]

    if "Ticker" not in df.columns:
        return []

    return [str(ticker).strip().upper() for ticker in df["Ticker"].tolist() if isinstance(ticker, str) and ticker.strip()]


def collect_all_exchange_tickers(
    exchanges: List[str] = ["NYSE", "NASDAQ"],
    min_volume: int = 1500000,
    min_close: float = 5.0,
    limit: int = 5000,
 ) -> Dict[str, List[str]]:
    """Collect high-volume and high-close tickers across requested exchanges."""
    results: Dict[str, List[str]] = {}
    for ex in exchanges:
        results[ex] = collect_high_volume_close_tickers(ex, min_volume=min_volume, min_close=min_close, limit=limit)
    return results


