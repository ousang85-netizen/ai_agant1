"""Simple backtesting for two-month high with volume spike strategy."""

from dataclasses import dataclass
from typing import List, Dict, Optional

import pandas as pd
import yfinance as yf


@dataclass
class Trade:
    date: pd.Timestamp
    symbol: str
    action: str
    price: float
    shares: int
    cash: float
    holdings_value: float
    total_value: float


@dataclass
class BacktestResult:
    symbol: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    trades: List[Trade]
    final_cash: float
    final_value: float
    returns: float
    hit_rate: float


def get_daily_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, progress=False, group_by='column', auto_adjust=False)
    if df is None or df.empty:
        raise ValueError(f"No data for {symbol}")

    if isinstance(df.columns, pd.MultiIndex):
        # For multiindex data, choose symbol columns if present in level 1.
        if symbol in df.columns.get_level_values(1):
            df = df.xs(symbol, axis=1, level=1)
        elif "Close" in df.columns.get_level_values(0):
            df = df.droplevel(1, axis=1)
        else:
            df = df.iloc[:, :].copy()

    df = df.reset_index()
    required = {"Date", "Close", "Volume"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"Missing required columns for {symbol}: {df.columns.tolist()}")
    return df


def is_two_month_high(df: pd.DataFrame, index: int, months: int = 2) -> bool:
    if index < 1:
        return False
    lookback = 42 * months
    start = max(0, index - lookback)
    period_high = df.loc[start:index - 1, "Close"].max()
    today_close = float(df.loc[index, "Close"])
    if pd.isna(period_high) or pd.isna(today_close):
        return False
    return today_close == float(period_high)


def volume_spike(df: pd.DataFrame, index: int, spike_factor: float = 1.5, window: int = 20) -> bool:
    if index < window:
        return False
    avg_vol = df.loc[index - window:index - 1, "Volume"].mean()
    today_vol = float(df.loc[index, "Volume"])
    if pd.isna(avg_vol) or pd.isna(today_vol) or avg_vol <= 0:
        return False
    return today_vol > avg_vol * spike_factor


def backtest_symbol(
    symbol: str,
    start: str,
    end: str,
    initial_cash: float = 100000,
    max_positions: int = 1,
    risk_pct: float = 0.01,
) -> BacktestResult:
    df = get_daily_data(symbol, start, end)
    trades: List[Trade] = []
    cash = initial_cash
    shares = 0
    holdings_value = 0.0

    for i in range(1, len(df)-1):
        if is_two_month_high(df, i) and volume_spike(df, i):
            if shares == 0:
                entry_price = float(df.loc[i, "Close"])
                purchase_amount = min(cash, initial_cash * 0.1)
                if purchase_amount < 1:
                    continue
                shares = int(purchase_amount // entry_price)
                if shares <= 0:
                    continue
                cash -= shares * entry_price
                holdings_value = shares * entry_price
                total_value = cash + holdings_value
                trades.append(
                    Trade(
                        date=df.loc[i, "Date"],
                        symbol=symbol,
                        action="buy",
                        price=entry_price,
                        shares=shares,
                        cash=cash,
                        holdings_value=holdings_value,
                        total_value=total_value,
                    )
                )
        if shares > 0:
            # Exit at next day close (simple hold for one day)
            exit_price = float(df.loc[i+1, "high"]) * 0.99
            cash += shares * exit_price # assume 1% slippage
            holdings_value = 0.0
            total_value = cash
            trades.append(
                Trade(
                    date=df.loc[i+1, "Date"],
                    symbol=symbol,
                    action="sell",
                    price=exit_price,  # assume 1% slippage
                    shares=shares,
                    cash=cash,
                    holdings_value=holdings_value,
                    total_value=total_value,
                )
            )
            shares = 0

    final_value = cash + shares * (float(df.iloc[-1]["Close"]) if shares else 0)
    returns = (final_value - initial_cash) / initial_cash
    wins = 0
    total_sells = 0
    for idx, t in enumerate(trades):
        if t.action == "sell" and idx > 0:
            prev = trades[idx - 1]
            if prev.action == "buy" and t.price > prev.price:
                wins += 1
            total_sells += 1
    hit_rate = (wins / total_sells) if total_sells > 0 else 0.0

    return BacktestResult(
        symbol=symbol,
        start_date=pd.to_datetime(start),
        end_date=pd.to_datetime(end),
        trades=trades,
        final_cash=cash,
        final_value=final_value,
        returns=returns,
        hit_rate=hit_rate,
    )


def backtest_portfolio(symbols: List[str], start: str, end: str, initial_cash: float = 100000) -> Dict[str, BacktestResult]:
    results: Dict[str, BacktestResult] = {}
    for s in symbols:
        try:
            results[s] = backtest_symbol(s, start, end, initial_cash=initial_cash)
        except Exception:
            continue
    return results


def backtest_from_csv(csv_path: str, start: str, end: str, initial_cash: float = 100000) -> Dict[str, BacktestResult]:
    df = pd.read_csv(csv_path)
    if "ticker" not in df.columns:
        raise ValueError("scan_results.csv must have a 'ticker' column")
    symbols = df["ticker"].astype(str).str.strip().dropna().unique().tolist()
    return backtest_portfolio(symbols, start, end, initial_cash=initial_cash)


def print_backtest(results: Dict[str, BacktestResult]):
    total_returns = 0.0
    total_wins = 0
    total_trades = 0

    with open("backtest_results.txt", "w") as f:
        for symbol, result in results.items():
            if result.trades:
                print(f"{symbol}: {result.returns:.2%} return, hit rate {result.hit_rate:.2%}, trades {len(result.trades)}", file=f)
                total_returns += result.returns
                total_wins += int(result.hit_rate * len(result.trades))/2
                total_trades += len(result.trades)/2
        print(f"total: trades:{total_trades} wins:{total_wins}  total_return:{total_returns:.2%}")
        print(f"total: trades:{total_trades} wins:{total_wins}  total_return:{total_returns:.2%}", file=f)



    f.close()

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backtest two-month-high + volume spike strategy.")
    parser.add_argument("--symbol", help="Ticker symbol to backtest", default=None)
    parser.add_argument("--start", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2025-01-01", help="End date YYYY-MM-DD")
    parser.add_argument("--from-csv", action="store_true", help="Backtest all tickers from scan_results.csv")
    parser.add_argument("--initial-cash", type=float, default=100000, help="Initial cash")
    args = parser.parse_args()

    if args.from_csv:
        results = backtest_from_csv("scan_results.csv", args.start, args.end, initial_cash=args.initial_cash)
        print_backtest(results)
    elif args.symbol:
        result = backtest_symbol(args.symbol, args.start, args.end, initial_cash=args.initial_cash)
        if result.trades != 0:
            print(f"Symbol: {result.symbol}")
            print(f"Period: {result.start_date.date()} to {result.end_date.date()}")
            print(f"Returns: {result.returns:.2%}")
            print(f"Hit Rate: {result.hit_rate:.2%}")
            print(f"Trades: {len(result.trades)}")
        else:
            pass
    else:
        parser.error("Please provide --symbol or --from-csv")


if __name__ == "__main__":
    main()
