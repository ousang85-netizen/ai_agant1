import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
import pyttsx3
import time
from datetime import date, datetime, timedelta

from schwab import SchwabClient
from data import get_data

class TechnicalAnalyzer:

    stock_list = ["^VIX", "spy", "qqq", "smh", "lrcx", "glw", "dram", "aaoi", "amzn", "orcl", "now", "strl", "aehr",
                  "nvda", "amd", "tsla", "aapl", "msft", "googl", "meta", "intc", "simo", "mu", "arm",
                  "sndk", "amd", "mrvl", "dell", "net", "skhy", "be", "wdc", "secz", "ceg","f", "ibm", "slv", "fcx",
                  "pfe", "mrna", "twst", "brkr", "ilmn", "ibb", "arkg", "labu", "tem", "ntra", "bntx","mrvi", "ions", "lly","ibit","rcl",
                  "afrm", "akam", "alab", "crcl", "crsp", "fsly", "gdx", "ionq", "stx", "ttmi", "avav", "cohr","p", "xbi",
                  "inod", "qcom", "crwd", "twlo", "cost", "avgo", "jpm",
                  "xlv", "xlre", "xle", "xlp", "xlu", "cboe"]    

    stock_info = {}
    #end_date = datetime.now()
    _schwab_client = None  # Placeholder for SchwabClient instance
    _initialized = False
    #_text_to_speech = None
    def check_rising_price(self, history: pd.DataFrame, lookback: int = 10) -> dict:
        """Find the previous low and report the price recovery from that point."""
        if lookback < 1:
            raise ValueError("lookback must be at least 1")
        if "Close" not in history:
            raise ValueError("history must contain a 'Close' column")
        if len(history) <= lookback:
            raise ValueError("history does not contain enough price data")

        close_prices = history["Close"]
        if isinstance(close_prices, pd.DataFrame):
            if close_prices.shape[1] != 1:
                raise ValueError("history must contain one 'Close' price series")
            close_prices = close_prices.iloc[:, 0]
        current_price = float(pd.to_numeric(close_prices.iloc[-1]))
        low_column = "Low" if "Low" in history else "Close"
        previous_prices = history[low_column]
        if isinstance(previous_prices, pd.DataFrame):
            if previous_prices.shape[1] != 1:
                raise ValueError("history must contain one price series")
            previous_prices = previous_prices.iloc[:, 0]
        previous_prices = pd.to_numeric(
            previous_prices.iloc[-lookback - 1:-1], errors="coerce"
        ).dropna()
        if previous_prices.empty:
            raise ValueError("history does not contain valid previous prices")

        low_position = previous_prices.idxmin()
        start_price = float(previous_prices.loc[low_position])
        if start_price <= 0:
            raise ValueError("previous lowest price must be greater than zero")

        price_change = current_price - start_price
        percent_change = price_change / start_price * 100
        return {
            "is_rising": price_change > 0,
            "low_date": low_position,
            "low_price": start_price,
            "current_price": current_price,
            "price_change": price_change,
            "percent_change": percent_change,
        }

    def __init__(self):
        """Downloads historical stock data and calculates specified EMAs."""
        # Fetch historical data from Yahoo Finance

        if TechnicalAnalyzer._initialized is True:
            print ("TechnicalAnalyzer already initialized")
            return None
        
        #self._text_to_speech = pyttsx3.init()
        #self._text_to_speech.setProperty('rate', 150)
        for ticker in self.stock_list:
            self.fetch_data(ticker, '1y', '1d')

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
    
    def speak(self, text):

        text_to_speech = pyttsx3.init()
        text_to_speech.setProperty('rate', 150)
        text_to_speech.setProperty('volume', 0.05)

        text_to_speech.say(text)

        # Block the script until the speaking is finished
        text_to_speech.runAndWait()
        time.sleep(1)

    def fetch_data(self, symbol,  data_period: str = "1y", interval: str = "1d"):
        """Fetch historical stock data from Yahoo Finance."""
        print(f"Fetching data for {symbol}...")
        data = get_data(symbol, period=data_period, interval=interval)
        if data.empty:
            raise ValueError(
                f"No data found for {symbol}. Check ticker symbol or date range."
            )

        ## calculate ATR
        high_low = data["High"] - data["Low"]
        high_close = abs(data["High"] - data["Close"].shift())
        low_close = abs(data["Low"] - data["Close"].shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        new_ele = {
            "history": data,
            "ema5": data["Close"].ewm(span=5, adjust=False).mean(),
            "ema10": data["Close"].ewm(span=10, adjust=False).mean(),
            "ema20": data["Close"].ewm(span=20, adjust=False).mean(),
            "ema50": data["Close"].ewm(span=50, adjust=False).mean(),
            "ema100": data["Close"].ewm(span=100, adjust=False).mean(),
            "ema150": data["Close"].ewm(span=150, adjust=False).mean(),
            "ema200": data["Close"].ewm(span=200, adjust=False).mean(),
            "atr":  true_range.ewm(alpha=1/14, adjust=False).mean(),
        }
        self.stock_info[symbol] = new_ele

    def market_open_minute(self):
        """Check if the current time is within the first 15 minutes of market open."""
        now = datetime.now()
        if now.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            return -1
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
            #print(f"Market open minute: {minutes}")
            return None
        doji_list = []
        for symbol in self.stock_list:
            data = self._schwab_client.get_quote(symbol)

            if symbol == '^VIX':
                upper_symbol = '$VIX'
            else:
                upper_symbol = symbol.upper()

            high = data[upper_symbol]['quote']['highPrice']
            low = data[upper_symbol]['quote']['lowPrice']
            open_price = data[upper_symbol]['quote']['openPrice']
            close = data[upper_symbol]['quote']['lastPrice']

            if open_price < 0.1:
                continue
            data = self.stock_info.get(symbol, {}).get("history")
            max_of_last_5 = data["High"].iloc[-5:-1].max()
            min_of_last_5 = data["Low"].iloc[-5:-1].min()

            daily_range = high - low
            open_close_diff = abs(close - open_price)

            if open_close_diff * 10 < daily_range:
                if max_of_last_5.iloc[0] < high or min_of_last_5.iloc[0] > low:
                    doji_list.append(symbol)

        print(f"Doji: {doji_list}")
        return None

    def vix_elevated(self):
            quote = self._schwab_client.get_quote("$VIX")
            high = quote["$VIX"]['quote']['lastPrice']
            data = self.stock_info.get("^VIX", {}).get("history")
            if high-0.7 > data['Close'].iloc[-2]['^VIX']:
                print(f"!!! VIX is elevated {data['Close'].iloc[-2]['^VIX']}!!!")
            return None
    def check_with_ema(self):
        at_ema = { "ema10":[], "ema20":[], "ema50":[], "ema100":[], "ema150":[], "ema200":[]}
        perfect_up_trend = []
        ema10_down = []
                                                        
        for symbol in self.stock_list:
            if symbol.startswith("^"):
                continue
            quote = self._schwab_client.get_quote(symbol)
            atr = self.stock_info.get(symbol, {}).get("atr").iloc[-1]
            ema10_val = self.stock_info.get(symbol, {}).get("ema10").iloc[-1][symbol.upper()]
            ema20_val = self.stock_info.get(symbol, {}).get("ema20").iloc[-1][symbol.upper()]
            ema50_val = self.stock_info.get(symbol, {}).get("ema50").iloc[-1][symbol.upper()]
            ema100_val = self.stock_info.get(symbol, {}).get("ema100").iloc[-1][symbol.upper()]
            ema150_val = self.stock_info.get(symbol, {}).get("ema150").iloc[-1][symbol.upper()]
            ema200_val = self.stock_info.get(symbol, {}).get("ema200").iloc[-1][symbol.upper()]
            emas = {
                "ema10": ema10_val,
                "ema20": ema20_val,
                "ema50": ema50_val,
                "ema100": ema100_val,
                "ema150": ema150_val,
                "ema200": ema200_val,
            }
  
            cur = quote[symbol.upper()]['quote']['lastPrice']  # need verify at market time
            #cur_low = quote[symbol.upper()]['quote']['lowPrice']
            prev_val = 1000000.0 # a number higher enough to beyond all stock price
            text = ""
            for key, value in emas.items():
                if value > prev_val:
                    prev_val = -1.0 # not in order, so not a perfect uptrend
                else:
                    prev_val = value
                if abs(cur - value)/atr < 0.2:
                    #at_ema[key].append(f"{symbol}({cur:.2f},{value:.2f},{atr:.2f})")
                    #at_ema[key].append(f"{symbol},atr={atr:.2f}")
                    text = key
            if prev_val > 0.0:
                #text += f"{symbol} is in perfect uptrend"
                perfect_up_trend.append(symbol)
            ema10_val1 = self.stock_info.get(symbol, {}).get("ema10").iloc[-1][symbol.upper()] 
            ema10_val2 = self.stock_info.get(symbol, {}).get("ema10").iloc[-2][symbol.upper()] 
            ema10_val3 = self.stock_info.get(symbol, {}).get("ema10").iloc[-3][symbol.upper()] 
            
            if ema10_val1 < ema10_val2 and ema10_val2 < ema10_val3:
                ema10_down.append(symbol)

            if text:
                at_ema[text].append(f"{symbol},atr={atr:.2f}")

        for key, value in at_ema.items():
            if value:
                print(f"at {key}: {value}")
        if perfect_up_trend:
            print(f"In perfect uptrend: {perfect_up_trend}")
        if ema10_down:
            print(f"ema10 down: {ema10_down}")
                                            
        #print("\n\n")
        return None

    def get_atr(self, symbol):
        if symbol in self.stock_list:
            atr = self.stock_info.get(symbol, {}).get("atr").dropna().iloc[-1]
            return atr

        print(f"Fetching data for {symbol}...")
        data = get_data(symbol, period="3mo", interval='1d')
        if data.empty:
            raise ValueError(
                f"No data found for {symbol}. Check ticker symbol or date range."
            )
                ## calculate ATR
        high_low = data["High"] - data["Low"]
        high_close = abs(data["High"] - data["Close"].shift())
        low_close = abs(data["Low"] - data["Close"].shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr =  true_range.ewm(alpha=1/14, adjust=False).mean()

        return atr.iloc[-1]
    
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
    analyzer.speak("Hi, you know how to sell ?")
    analyzer.speak("Hi, you know how to buy ?")
    #analyzer.plot_data()
    print("Technical analysis completed.")