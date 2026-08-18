"""Placeholder utilities for interacting with a Fidelity brokerage account."""

from typing import Dict, List


def get_stock_holdings() -> List[Dict]:
    """Return a list of stock holdings in the Fidelity account.

    In a real implementation this would call Fidelity's API, perform
    authentication, and parse the response. For now it returns a dummy
    response so other code can be developed around it.

    Returns:
        A list of dicts with ``symbol`` and ``shares`` keys.
    """
    # TODO: replace with real API calls using OAuth / API key
    return [
        {"symbol": "AAPL", "shares": 150},
        {"symbol": "MSFT", "shares": 50},
    ]


def get_option_holdings() -> List[Dict]:
    """Return a list of option holdings in the Fidelity account.

    Each entry could include contract details like symbol, expiry,
    strike, type (call/put), and quantity. Currently returns stub data.
    """
    return [
        {"symbol": "AAPL", "expiry": "2026-06-19", "strike": 150, "type": "call", "contracts": 2},
    ]
