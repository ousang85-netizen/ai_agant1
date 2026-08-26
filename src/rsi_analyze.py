import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pandas_ta as ta
from scipy.signal import argrelelextrema
import yfinance as yf


def fetch_and_prepare_data(ticker, start_date, end_date):
    """Downloads stock data and calculates 14-period RSI."""
    df = yf.download(ticker, start=start_date, end=end_date)
    # Ensure correct data format
    df.columns = [col.lower() for col in df.columns]

    # Calculate 14-period RSI using standard Wilder's EMA method
    df["rsi"] = ta.rsi(df["close"], length=14)
    df.dropna(inplace=True)
    return df


def find_local_extrema(df, order=5):
    """Finds local maxima (peaks) and minima (troughs) using SciPy."""
    # order controls the sensitivity: higher order means wider peaks/troughs
    df["local_max"] = df["close"].iloc[
        argrelelextrema(df["close"].values, np.greater, order=order)[0]
    ]
    df["local_min"] = df["close"].iloc[
        argrelelextrema(df["close"].values, np.less, order=order)[0]
    ]

    df["rsi_max"] = df["rsi"].iloc[
        argrelelextrema(df["rsi"].values, np.greater, order=order)[0]
    ]
    df["rsi_min"] = df["rsi"].iloc[
        argrelelextrema(df["rsi"].values, np.less, order=order)[0]
    ]
    return df


def detect_divergence(df, lookback=5):
    """Scans historical extrema to identify bullish and bearish divergences."""
    df["bullish_divergence"] = False
    df["bearish_divergence"] = False

    # Get indices of local extrema
    min_indices = df[df["local_min"].notna()].index
    max_indices = df[df["local_max"].notna()].index

    # 1. Detect Regular Bullish Divergence (Price Lower Low + RSI Higher Low)
    for i in range(1, len(min_indices)):
        current_idx = min_indices[i]
        # Look back within a reasonable window of previous troughs
        for j in range(max(0, i - lookback), i):
            prev_idx = min_indices[j]

            price_lower_low = (
                df.loc[current_idx, "close"] < df.loc[prev_idx, "close"]
            )
            rsi_higher_low = (
                df.loc[current_idx, "rsi"] > df.loc[prev_idx, "rsi"]
            )

            # Confirm both price and RSI actually formed a valid validation point
            if price_lower_low and rsi_higher_low:
                df.at[current_idx, "bullish_divergence"] = True
                break

    # 2. Detect Regular Bearish Divergence (Price Higher High + RSI Lower High)
    for i in range(1, len(max_indices)):
        current_idx = max_indices[i]
        for j in range(max(0, i - lookback), i):
            prev_idx = max_indices[j]

            price_higher_high = (
                df.loc[current_idx, "close"] > df.loc[prev_idx, "close"]
            )
            rsi_lower_high = (
                df.loc[current_idx, "rsi"] < df.loc[prev_idx, "rsi"]
            )

            if price_higher_high and rsi_lower_high:
                df.at[current_idx, "bearish_divergence"] = True
                break

    return df


def plot_signals(df, ticker):
    """Visualizes the closing prices, RSI, and marked divergence points."""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )

    # Plot Close Price
    ax1.plot(df.index, df["close"], label="Close Price", color="blue", alpha=0.6)
    bullish_signals = df[df["bullish_divergence"] == True]
    bearish_signals = df[df["bearish_divergence"] == True]

    ax1.scatter(
        bullish_signals.index,
        bullish_signals["close"],
        color="green",
        marker="^",
        s=100,
        label="Bullish Divergence",
    )
    ax1.scatter(
        bearish_signals.index,
        bearish_signals["close"],
        color="red",
        marker="v",
        s=100,
        label="Bearish Divergence",
    )
    ax1.set_title(f"{ticker} Price & RSI Divergence Detection")
    ax1.set_ylabel("Price ($)")
    ax1.legend()
    ax1.grid()

    # Plot RSI
    ax2.plot(df.index, df["rsi"], label="RSI (14)", color="purple", alpha=0.7)
    ax2.axhline(70, color="red", linestyle="--", alpha=0.5, label="Overbought")
    ax2.axhline(30, color="green", linestyle="--", alpha=0.5, label="Oversold")

    # Match indicator markers
    ax2.scatter(
        bullish_signals.index,
        bullish_signals["rsi"],
        color="green",
        marker="^",
        s=100,
    )
    ax2.scatter(
        bearish_signals.index,
        bearish_signals["rsi"],
        color="red",
        marker="v",
        s=100,
    )
    ax2.set_ylabel("RSI Value")
    ax2.set_xlabel("Date")
    ax2.legend(loc="lower left")
    ax2.grid()

    plt.tight_layout()
    plt.show()


# --- Execution Flow ---
if __name__ == "__main__":
    TICKER = "AAPL"  # Example stock
    START = "2024-01-01"
    END = "2026-01-01"

    # Process pipeline
    data = fetch_and_prepare_data(TICKER, START, END)
    data_with_extrema = find_local_extrema(data, order=5)
    final_data = detect_divergence(data_with_extrema, lookback=3)

    # Print out dates where divergences were flagged
    bulls = final_data[final_data["bullish_divergence"] == True]
    bears = final_data[final_data["bearish_divergence"] == True]

    print(f"\nDetected {len(bulls)} Bullish Divergence dates.")
    print(f"Detected {len(bears)} Bearish Divergence dates.\n")

    # Render Visual Chart
    plot_signals(final_data, TICKER)
