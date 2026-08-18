import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from datetime import date, datetime, timedelta

from schwab import SchwabClient

class TechnicalAnalyzer:

    stock_list = ["smh", "qqq", "lrcx", "glw", "dram", "aaoi", "amzn", "orcl", "now", "strl", 
                  "nvda", "amd", "tsla", "aapl", "msft", "googl", "meta", "intc", "simo", "mu", 
                  "sndk", "tsla", "nvda", "amd", "mrvl", "msft", "intc"]    
    stock_info = {}
    start_date = "2025-08-18"
    end_date = "2026-08-18"
    #end_date = datetime.now()
    _schwab_client = None  # Placeholder for SchwabClient instance
    _initialized = False

    def __init__(self):
        """Downloads historical stock data and calculates specified EMAs."""
        # Fetch historical data from Yahoo Finance

        if TechnicalAnalyzer._initialized is True:
            print ("TechnicalAnalyzer already initialized")
            return None
        
        self.end_date = datetime.now()
        self.start_date = self.end_date - timedelta(days=365)  # Last 1 year

        for ticker in self.stock_list:
            self.fetch_data(ticker, self.start_date, self.end_date)

        '''
        # Calculate EMAs using pandas ewm (Exponential Weighted Moving) method
        for window in windows:
            # adjust=False implements the traditional recursive EMA formula
            df[f"EMA_{window}"] = (
                df["Close"].ewm(span=window, adjust=False).mean()
            )
        '''
        TechnicalAnalyzer._schwab_client = SchwabClient()  # Initialize SchwabClient instance
        TechnicalAnalyzer._initialized = True
        return None

    def fetch_data(self, symbol,  start_date=None, end_date=None):
        """Fetch historical stock data from Yahoo Finance."""
        print(f"Fetching data for {symbol}...")
        data = yf.download(symbol, start=start_date, end=end_date)
        if data.empty:
            raise ValueError(
                f"No data found for {symbol}. Check ticker symbol or date range."
            )
        new_ele = {
            "history": data,
            "ema20": data["Close"].ewm(span=20, adjust=False).mean(),
            "ema50": data["Close"].ewm(span=50, adjust=False).mean(),
            "ema100": data["Close"].ewm(span=100, adjust=False).mean(),
            "ema150": data["Close"].ewm(span=150, adjust=False).mean(),
            "ema200": data["Close"].ewm(span=200, adjust=False).mean(),
        }
        self.stock_info[symbol] = new_ele

    def market_open_minute(self):
        """Check if the current time is within the first 15 minutes of market open."""
        now = datetime.now()
        if now.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            return None
        market_open_time = now.replace(hour=6, minute=30, second=0, microsecond=0)
        time_diff = now - market_open_time
        return time_diff.total_seconds() // 60  # Return minutes since market open

    def show_doji(self):
        """Checks if a stock closed near its open after a strong swing.

        - swing_threshold: Minimum high-to-low range percentage (e.g., 3%).
        - close_threshold: Max open-to-close difference percentage (e.g., 0.5%).
        """

        minutes =  self.market_open_minute()
        if minutes is None or minutes < 330:
            #eturn False  # Only check during the first 15 minutes of market open
            print(f"Market open minute: {minutes}")
        doji_list = []
        for symbol in self.stock_list:
            data = self._schwab_client.get_quote(symbol)
            upper_symbol = symbol.upper()
            high = data[upper_symbol]['quote']['highPrice']
            low = data[upper_symbol]['quote']['lowPrice']
            open_price = data[upper_symbol]['quote']['openPrice']
            close = data[upper_symbol]['quote']['mark']
            

            daily_range = (high - low) / open_price
            open_close_diff = abs(close - open_price) / open_price

            # Check if the swing is large and the close is near the open
            #is_strong_swing = daily_range >= swing_threshold
            #is_closed_near_open = open_close_diff <= close_threshold

            #return is_strong_swing and is_closed_near_open   
            if open_close_diff * 6 < daily_range:
                doji_list.append(symbol)

        print(f"Doji: {doji_list}")
        return None

    def plot_data(self):
        """Plot the stock's closing price and EMAs."""

        data = self.stock_info.get(self.stock_list[0], {}).get("history")
        
        plt.figure(figsize=(14, 7))
        plt.plot(data.index, data["Close"], label="Close Price", color="blue")
        
        # Plot all EMA columns
        ema20 = self.stock_info.get(self.stock_list[0], {}).get("ema20")
        ema50 = self.stock_info.get(self.stock_list[0], {}).get("ema50")
        ema100 = self.stock_info.get(self.stock_list[0], {}).get("ema100")
        ema150 = self.stock_info.get(self.stock_list[0], {}).get("ema150")
        ema200 = self.stock_info.get(self.stock_list[0], {}).get("ema200")
        plt.plot(data.index, ema20, label="EMA 20")
        plt.plot(data.index, ema50, label="EMA 50")
        plt.plot(data.index, ema100, label="EMA 100")
        plt.plot(data.index, ema150, label="EMA 150")
        plt.plot(data.index, ema200, label="EMA 200")
        
        plt.title(f"{self.stock_list[0]} Price and EMAs")
        plt.xlabel("Date")
        plt.ylabel("Price")
        plt.legend()
        plt.grid()
        plt.show()

if __name__ == "__main__":
    analyzer = TechnicalAnalyzer()
    analyzer.plot_data()
    print("Technical analysis completed.")